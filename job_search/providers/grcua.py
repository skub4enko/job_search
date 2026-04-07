from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from job_search.extract import extract_emails, extract_phones, is_remote
from job_search.models import Job
from job_search.providers.base import Provider
from job_search.timeutil import now_iso


class GrcUAProvider(Provider):
    source = "grcua"
    _BASE = "https://jobs.grc.ua/"

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
        # Wordpress-подобный сайт: поиск через ?s=... и пагинация /page/2/
        q = quote_plus(query)
        if remote_only:
            base_url = f"{self._BASE}job-location/%D0%B2%D1%96%D0%B4%D0%B4%D0%B0%D0%BB%D0%B5%D0%BD%D0%B0-%D1%80%D0%BE%D0%B1%D0%BE%D1%82%D0%B0/"
        else:
            base_url = self._BASE

        urls: list[str] = []
        for page in range(1, max_pages + 1):
            if progress_cb:
                progress_cb(page, max_pages)
            page_url = base_url
            if page > 1:
                page_url = urljoin(base_url, f"page/{page}/")
            if q:
                page_url += ("?" if "?" not in page_url else "&") + f"s={q}"

            r = await self._fetcher.get_text(page_url)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "lxml")

            for a in soup.select("a[href]"):
                href = (a.get("href") or "").strip()
                if not href:
                    continue
                # вакансии обычно это посты без /category/ и без фильтров
                if href.startswith(self._BASE) and "/job-" in href:
                    urls.append(href)
                elif href.startswith(self._BASE) and re.search(r"/\d{4}/\d{2}/", href):
                    urls.append(href)

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
        # иногда компания в meta или в блоке "Company"
        m = re.search(r"\b(Company|Компанія|Компания)\s*:?\s*(.+)", page_text)
        if m:
            company = m.group(2).split("\n")[0].strip()

        location = ""
        # Location near breadcrumbs
        crumbs = soup.select("nav a, .breadcrumbs a")
        for c in crumbs:
            t = c.get_text(strip=True)
            if t and t.lower() not in {"home", "головна", "головная", "jobs"}:
                location = t

        published_at = ""
        time_el = soup.select_one("time")
        if time_el:
            published_at = (time_el.get("datetime") or "").strip() or time_el.get_text(strip=True)

        description = ""
        article = soup.select_one("article")
        if article:
            description = article.get_text("\n", strip=True)

        combined = "\n".join([title, company, location, description, page_text])
        remote = is_remote(combined)
        if remote_only and not remote:
            return None

        emails = extract_emails(combined)
        phones = extract_phones(combined)

        if not title:
            return None

        scraped_at = now_iso()
        return Job(
            source=self.source,
            url=url,
            title=title,
            company=company,
            location=location,
            salary="",
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
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out
