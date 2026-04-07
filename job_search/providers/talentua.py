from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from job_search.extract import extract_emails, extract_phones, is_remote
from job_search.models import Job
from job_search.providers.base import Provider
from job_search.timeutil import now_iso


class TalentUAProvider(Provider):
    source = "talentua"
    _BASE = "https://talent.ua/"

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
        # Best-effort: у Talent.UA страница поиска /ru/vacancies/search
        # На практике параметры могут меняться; поэтому делаем несколько вариантов URL.
        q_text = f"{query} remote" if remote_only else query
        q = quote_plus(q_text)

        candidates = [
            f"{self._BASE}ru/vacancies/search?query={q}",
            f"{self._BASE}ru/vacancies/search?q={q}",
            f"{self._BASE}ru/vacancies/search?search={q}",
            f"{self._BASE}en/vacancies/search?query={q}",
        ]

        urls: list[str] = []

        for base_url in candidates:
            for page in range(1, max_pages + 1):
                if progress_cb:
                    progress_cb(page, max_pages)
                page_url = base_url
                if page > 1:
                    page_url += ("&" if "?" in page_url else "?") + f"page={page}"

                r = await self._fetcher.get_text(page_url)
                if r.status_code != 200:
                    continue

                soup = BeautifulSoup(r.text, "lxml")
                for a in soup.select("a[href]"):
                    href = (a.get("href") or "").strip()
                    if not href:
                        continue
                    # вакансии: /ru/vacancies/12345-...
                    if re.search(r"/(ru|uk|en)/vacancies/\d+", href):
                        urls.append(urljoin(self._BASE, href))

                if urls:
                    break

            if urls:
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
        company_el = soup.select_one('.company a, a[href*="/company"], [class*="company"] a')
        if company_el:
            company = company_el.get_text(strip=True)

        location = ""
        loc_el = soup.select_one('.location, [class*="location"], [class*="city"]')
        if loc_el:
            location = loc_el.get_text(" ", strip=True)

        published_at = ""
        time_el = soup.select_one("time")
        if time_el:
            published_at = (time_el.get("datetime") or "").strip() or time_el.get_text(strip=True)

        description = ""
        desc_el = soup.select_one('.description, [class*="description"], article')
        if desc_el:
            description = desc_el.get_text("\n", strip=True)

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
