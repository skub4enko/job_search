from __future__ import annotations

import math
import os
from dataclasses import dataclass

import httpx

from job_search.extract import extract_emails, extract_phones, is_remote
from job_search.models import Job
from job_search.providers.base import Provider
from job_search.timeutil import now_iso


@dataclass(frozen=True, slots=True)
class _ApiVacancy:
    name: str
    cityName: str
    companyName: str
    date: str
    shortDescription: str
    salary: int
    notebookId: int
    id: int


class RabotaUAProvider(Provider):
    """Rabota.ua / Robota.ua provider via public API.

    Это самый стабильный способ получать выдачу без авторизации.

    API (пример из внешних реализаций):
    https://api.rabota.ua/vacancy/search?keyWords=python&count=59&page=0

    Поля `notebookId` и `id` используются для построения публичной ссылки:
    https://rabota.ua/ua/company{notebookId}/vacancy{id}
    """

    source = "rabotaua"
    _API = "https://api.rabota.ua/vacancy/search"

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
        self._jobs_by_url.clear()

        # Подмешиваем "віддалено" для лучшего покрытия украинской выдачи.
        q_text = f"{query} віддалено" if remote_only else query

        per_page = 59
        timeout = httpx.Timeout(self._fetcher._timeout)  # noqa: SLF001
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }

        urls: list[str] = []

        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            total_pages = None

            page = 0
            while page < max_pages:
                if progress_cb:
                    progress_cb(page + 1, max_pages)
                params = {"keyWords": q_text, "count": per_page, "page": page}
                try:
                    resp = await client.get(self._API, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    if self._fetcher.is_offline_error(e):
                        await self._fetcher.wait_for_internet()
                        continue
                    if self._verbose:
                        import sys

                        print(f"[{self.source}] api error page={page}: {e}", file=sys.stderr)
                    break

                if total_pages is None:
                    try:
                        total = int(data.get("total") or 0)
                    except Exception:
                        total = 0
                    total_pages = max(1, int(math.ceil(total / per_page))) if total else 1

                docs = data.get("documents") or []
                if not isinstance(docs, list) or not docs:
                    break

                for item in docs:
                    if not isinstance(item, dict):
                        continue
                    v = _parse_doc(item)
                    if v is None:
                        continue

                    url = f"https://rabota.ua/ua/company{v.notebookId}/vacancy{v.id}"

                    text_for_filters = "\n".join([v.name, v.companyName, v.cityName, v.shortDescription])
                    remote = is_remote(text_for_filters)
                    if remote_only and not remote:
                        continue

                    emails = extract_emails(text_for_filters)
                    phones = extract_phones(text_for_filters)

                    salary = str(v.salary) if v.salary else ""
                    published_at = (v.date or "").split("T")[0] if v.date else ""
                    scraped_at = now_iso()

                    job = Job(
                        source=self.source,
                        url=url,
                        title=v.name,
                        company=v.companyName,
                        location=v.cityName or ("Віддалено" if remote else ""),
                        salary=salary,
                        published_at=published_at,
                        remote=remote,
                        emails=emails,
                        phones=phones,
                        description=(v.shortDescription or "").replace("\u00a0", " ").strip(),
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

                if total_pages is not None and page + 1 >= total_pages:
                    break

                page += 1

        return urls

    async def parse_job(self, url: str, *, remote_only: bool, city: str) -> Job | None:
        job = self._jobs_by_url.get(url)
        if job is None:
            return None
        if remote_only and not job.remote:
            return None
        return job


def _parse_doc(d: dict) -> _ApiVacancy | None:
    try:
        return _ApiVacancy(
            name=str(d.get("name") or "").strip(),
            cityName=str(d.get("cityName") or "").strip(),
            companyName=str(d.get("companyName") or "").strip(),
            date=str(d.get("date") or "").strip(),
            shortDescription=str(d.get("shortDescription") or "").strip(),
            salary=int(d.get("salary") or 0),
            notebookId=int(d.get("notebookId") or 0),
            id=int(d.get("id") or 0),
        )
    except Exception:
        return None
