from __future__ import annotations

import re
import sys
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from job_search.extract import extract_emails, extract_phones, is_remote
from job_search.models import Job
from job_search.providers.base import Provider
from job_search.timeutil import now_iso


class WorkUAProvider(Provider):
    source = "workua"
    _BASE = "https://www.work.ua/"

    _PUBLISHED_RE = re.compile(r"(Опубліковано|Вакансія від|Опубликовано)\s*[:–-]?\s*(.+)", re.IGNORECASE)

    @staticmethod
    def _clean_published_at(value: str) -> str:
        s = re.sub(r"\s+", " ", (value or "").replace("\u00a0", " ")).strip()
        if not s:
            return ""

        # Work.ua often appends extra UI text after the date (e.g. "Зараз переглядають...").
        s = re.split(
            r"\b(Зараз|Схожі|Опис|Контакти|Відгукнутися|Показати|Умови|Вимоги|Обов[’']язки)\b",
            s,
            maxsplit=1,
        )[0].strip(" ,;|-")

        if len(s) <= 80:
            return s

        # If it's still huge, try to extract a date-like fragment.
        m = re.search(
            r"(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[^\d\s]{3,20}\s+\d{4})",
            s,
        )
        if m:
            return m.group(1).strip()

        return s[:80].rstrip()

    def _extract_published_at(self, soup: BeautifulSoup) -> str:
        # Use newlines for safer extraction; page_text (space-joined) can make regex consume the whole page.
        text_nl = soup.get_text("\n", strip=True)
        for line in text_nl.splitlines():
            m = self._PUBLISHED_RE.search(line)
            if not m:
                continue
            return self._clean_published_at(m.group(2))
        return ""

    async def search_job_urls(
        self,
        *,
        query: str,
        city: str,
        remote_only: bool,
        max_pages: int,
        limit: int,
        progress_cb=None,
    ) -> list[str]:
        """Поиск ссылок на вакансии."""
        city_text = "Дистанційно" if remote_only else city
        urls: list[str] = []
        q = quote_plus(query)
        c = quote_plus(city_text) if city_text else ""

        for page in range(1, max_pages + 1):
            if progress_cb:
                progress_cb(page, max_pages)

            page_url = f"{self._BASE}jobs/?search={q}"
            if c:
                page_url += f"&city={c}"
            if page > 1:
                page_url += f"&page={page}"

            r = await self._fetcher.get_text(page_url)
            if r.status_code != 200:
                if self._verbose:
                    print(f"[{self.source}] status={r.status_code} url={page_url}", file=sys.stderr)
                continue

            soup = BeautifulSoup(r.text, "lxml")

            # Ссылки на вакансии вида /jobs/123456/
            for a in soup.select("a[href]"):
                href = (a.get("href") or "").strip()
                if not href:
                    continue
                if re.match(r"^/jobs/\d+/?$", href) or re.search(r"/jobs/\d+/?$", href):
                    full_url = urljoin(self._BASE, href)
                    if full_url not in urls:
                        urls.append(full_url)

            if len(urls) >= limit:
                break

        return urls[:limit]

    async def parse_job(self, url: str, *, remote_only: bool, city: str) -> Job | None:
        """Парсинг одной вакансии."""
        r = await self._fetcher.get_text(url)
        if r.status_code != 200:
            if self._verbose:
                print(f"[{self.source}] status={r.status_code} url={url}", file=sys.stderr)
            return None

        soup = BeautifulSoup(r.text, "lxml")
        page_text = soup.get_text(" ", strip=True)  # для поиска ключевых слов

        # === Title ===
        h1 = soup.select_one("h1")
        title = h1.get_text(strip=True) if h1 else ""
        if not title:
            return None

        # === Company ===
        company_el = soup.select_one('a[href*="/jobs/by-company/"]')
        company = company_el.get_text(strip=True) if company_el else ""

        # === Location + Remote ===
        location = ""
        remote = is_remote(page_text) or "дистанц" in page_text.lower() or "віддален" in page_text.lower()

        # Пытаемся взять локацию из иконки карты (если есть)
        loc_icon = soup.select_one(".glyphicon-map-marker, .icon-map-marker")
        if loc_icon:
            li = loc_icon.find_parent("li") or loc_icon.find_parent("div")
            if li:
                location = li.get_text(" ", strip=True).replace(" ", " ").strip(" ,")

        # Если локация не найдена — проверяем на "Дистанційна робота"
        if not location:
            if remote or "дистанційна робота" in page_text.lower():
                location = "Дистанційно"
                remote = True

        # === Salary ===
        salary = ""
        salary_el = soup.select_one(".salary, .add-top-sm .h2, h2[class*='salary']")
        if salary_el:
            txt = salary_el.get_text(" ", strip=True)
            if re.search(r"\d", txt) and any(k in txt.lower() for k in ["грн", "uah", "₴", "$", "€"]):
                salary = txt

        # === Published date ===
        published_at = ""
        published_at = self._extract_published_at(soup)

        # === Remote filter ===
        if remote_only and not remote:
            if self._verbose:
                print(f"[{self.source}] skip non-remote url={url}", file=sys.stderr)
            return None

        # === Description ===
        desc_el = soup.select_one(".job-description, #job-description, .text, article, .description")
        description = desc_el.get_text("\n", strip=True) if desc_el else ""

        # === Contacts ===
        emails = extract_emails(page_text)
        phones = extract_phones(page_text)

        scraped_at = now_iso()

        return Job(
            source=self.source,
            url=url,
            title=title,
            company=company,
            location=location,
            salary=salary,
            published_at=published_at,
            remote=remote,
            emails=emails,
            phones=phones,
            description=description,
            scraped_at=scraped_at,
            first_seen_at=scraped_at,
            last_seen_at=scraped_at,
            is_active=True,
        )


def _uniq(values: list[str]) -> list[str]:
    """Удаление дубликатов с сохранением порядка."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out
