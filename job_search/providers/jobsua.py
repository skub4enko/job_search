from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from job_search.extract import extract_emails, extract_phones, is_remote
from job_search.models import Job
from job_search.providers.base import Provider
from job_search.timeutil import now_iso


class JobsUAProvider(Provider):
    source = "jobsua"
    _BASE = "https://jobs.ua/"

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
        # Jobs.ua выдачу формирует по slug-странице:
        # https://jobs.ua/rus/vacancy/rabota-<query> и пагинация /page-2
        q_text = f"{query} удаленно" if remote_only else query
        slug = _to_slug(q_text)
        base_url = f"{self._BASE}rus/vacancy/rabota-{slug}"

        urls: list[str] = []
        for page in range(1, max_pages + 1):
            if progress_cb:
                progress_cb(page, max_pages)
            page_url = base_url if page == 1 else f"{base_url}/page-{page}"
            r = await self._fetcher.get_text(page_url)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "lxml")

            for a in soup.select("a[href]"):
                href = (a.get("href") or "").strip()
                if not href:
                    continue

                # job page: /rus/job-...-123456
                if re.search(r"/(rus/)?job-[^\s/]+-\d+", href):
                    urls.append(urljoin(self._BASE, href))

            if len(urls) >= limit:
                break

        return _uniq(urls)[:limit]

    async def parse_job(self, url: str, *, remote_only: bool, city: str) -> Job | None:
        r = await self._fetcher.get_text(url)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "lxml")
        page_text = soup.get_text("\n", strip=True)

        h1 = soup.select_one("h1")
        title = h1.get_text(strip=True) if h1 else ""

        company = ""
        company_el = soup.select_one('a[href*="/rus/company"], a[href*="/company"]')
        if company_el:
            company = company_el.get_text(strip=True)

        location = ""
        # часто город в ссылке/плашке рядом с вакансией
        loc_el = soup.select_one('a[href*="/rus/vacancy/"][href*="city"], .city, [class*="city"]')
        if loc_el:
            location = loc_el.get_text(" ", strip=True)

        salary = ""
        salary_el = soup.select_one('.salary, [class*="salary"], .vacancy_salary')
        if salary_el:
            salary = salary_el.get_text(" ", strip=True)

        published_at = ""
        # даты часто вида "26.03.2026" или "Сегодня" в блоке
        m = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", page_text)
        if m:
            published_at = m.group(1)

        remote = is_remote(page_text) or ("удал" in page_text.lower())
        if remote_only and not remote:
            return None

        emails = extract_emails(page_text)
        phones = extract_phones(page_text)

        description = ""
        desc_el = soup.select_one('.vacancy_description, .description, [class*="description"], article')
        if desc_el:
            description = desc_el.get_text("\n", strip=True)

        if not title:
            return None

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


def _to_slug(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return quote(text, safe="-")


def _uniq(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out
