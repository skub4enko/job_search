from __future__ import annotations

import os
import sys

import httpx

from job_search.extract import extract_emails, extract_phones, is_remote
from job_search.models import Job
from job_search.providers.base import Provider
from job_search.timeutil import now_iso


class JoobleProvider(Provider):
    source = "jooble"
    _API_BASE = "https://jooble.org/api/"

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
        api_key = (os.getenv("JOOBLE_API_KEY") or "").strip()
        if not api_key:
            if self._verbose:
                print(f"[{self.source}] skipped: JOOBLE_API_KEY not set", file=sys.stderr)
            return []

        # Jooble — агрегатор. Фильтрации remote в API зависит от региона/параметров,
        # поэтому подмешиваем remote в ключевые слова и дополнительно фильтруем.
        keywords = f"{query} remote" if remote_only else query

        urls: list[str] = []
        self._jobs_by_url.clear()

        timeout = httpx.Timeout(self._fetcher._timeout)  # noqa: SLF001 (локальный проект)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            )
        }

        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            page = 1
            while page <= max_pages:
                if progress_cb:
                    progress_cb(page, max_pages)
                payload = {
                    "keywords": keywords,
                    "location": city or "Ukraine",
                    "page": page,
                }
                try:
                    resp = await client.post(f"{self._API_BASE}{api_key}", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    if self._fetcher.is_offline_error(e):
                        await self._fetcher.wait_for_internet()
                        continue
                    if self._verbose:
                        print(f"[{self.source}] api error: {e}", file=sys.stderr)
                    break

                jobs = data.get("jobs") or []
                if not isinstance(jobs, list) or not jobs:
                    break

                for item in jobs:
                    if not isinstance(item, dict):
                        continue

                    url = (item.get("link") or item.get("url") or "").strip()
                    if not url:
                        continue

                    title = str(item.get("title") or "").strip()
                    company = str(item.get("company") or item.get("companyName") or "").strip()
                    location = str(item.get("location") or "").strip()
                    salary = str(item.get("salary") or "").strip()
                    published_at = str(item.get("updated") or item.get("date") or "").strip()
                    snippet = str(item.get("snippet") or item.get("description") or "").strip()

                    text_for_filters = "\n".join([title, company, location, snippet])
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
                        location=location or ("Remote" if remote else ""),
                        salary=salary,
                        published_at=published_at,
                        remote=remote,
                        emails=emails,
                        phones=phones,
                        description=snippet,
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

                page += 1

        return urls

    async def parse_job(self, url: str, *, remote_only: bool, city: str) -> Job | None:
        # Данные уже пришли из API.
        job = self._jobs_by_url.get(url)
        if job is None:
            return None
        if remote_only and not job.remote:
            return None
        return job
