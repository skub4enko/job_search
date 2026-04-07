from __future__ import annotations

import os
from urllib.parse import quote_plus

import httpx

from job_search.extract import extract_emails, extract_phones, is_remote
from job_search.models import Job
from job_search.providers.base import Provider
from job_search.timeutil import now_iso


class IndeedProvider(Provider):
    """Indeed results via ScrapeOps Structured Data API.

    Notes:
    - Direct scraping of Indeed is often blocked; this provider uses a 3rd-party API.
    - Requires SCRAPEOPS_API_KEY env var (or pass via CLI and set env).
    """

    source = "indeed"
    _BASE = "https://proxy.scrapeops.io/v1/structured-data/indeed/job-search"

    def __init__(self, fetcher, *, verbose: bool):
        super().__init__(fetcher, verbose=verbose)
        self._jobs_by_url: dict[str, Job] = {}

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
        api_key = (os.getenv("SCRAPEOPS_API_KEY") or "").strip()
        if not api_key:
            return []

        urls: list[str] = []
        self._jobs_by_url.clear()

        # Structured API возвращает страницы; location можно оставить пустым.
        location = city or "Ukraine"
        q = query
        if remote_only:
            q = f"{q} remote"

        timeout = httpx.Timeout(self._fetcher._timeout)  # noqa: SLF001 (локальный проект)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            )
        }

        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            for page in range(1, max_pages + 1):
                if progress_cb:
                    progress_cb(page, max_pages)
                params = {
                    "api_key": api_key,
                    "query": q,
                    "location": location,
                    "page": page,
                }
                try:
                    resp = await client.get(self._BASE, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    break

                jobs = data.get("jobs") or data.get("results") or []
                if not isinstance(jobs, list) or not jobs:
                    break

                for item in jobs:
                    if not isinstance(item, dict):
                        continue

                    url = str(item.get("job_url") or item.get("url") or item.get("link") or "").strip()
                    if not url:
                        continue

                    title = str(item.get("title") or "").strip()
                    company = str(item.get("company") or item.get("company_name") or "").strip()
                    loc = str(item.get("location") or item.get("job_location") or "").strip()
                    salary = str(item.get("salary") or item.get("salary_text") or "").strip()
                    published_at = str(item.get("date") or item.get("posted_at") or item.get("posted") or "").strip()
                    desc = str(item.get("description") or item.get("snippet") or "").strip()

                    text_for_filters = "\n".join([title, company, loc, desc])
                    remote = is_remote(text_for_filters)
                    if remote_only and not remote:
                        continue

                    emails = extract_emails(text_for_filters)
                    phones = extract_phones(text_for_filters)

                    scraped_at = now_iso()
                    job = Job(
                        source=self.source,
                        url=url,
                        title=title or "(no title)",
                        company=company,
                        location=loc or ("Remote" if remote else ""),
                        salary=salary,
                        published_at=published_at,
                        remote=remote,
                        emails=emails,
                        phones=phones,
                        description=desc,
                        scraped_at=scraped_at,
                        first_seen_at=scraped_at,
                        last_seen_at=scraped_at,
                        is_active=True,
                    )

                    if url not in self._jobs_by_url:
                        self._jobs_by_url[url] = job
                        urls.append(url)

                    if len(urls) >= limit:
                        return urls

        return urls

    async def parse_job(self, url: str, *, remote_only: bool, city: str) -> Job | None:
        job = self._jobs_by_url.get(url)
        if job is None:
            return None
        if remote_only and not job.remote:
            return None
        return job
