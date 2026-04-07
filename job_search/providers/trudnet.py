from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_search.extract import extract_emails, extract_phones, is_remote
from job_search.models import Job
from job_search.providers.base import Provider
from job_search.timeutil import now_iso


class TrudNetProvider(Provider):
    """Trud.net provider (best-effort).

    Trud.net listings often link out via /away/<id>/ URLs.
    To keep parsing stable, we build Job objects from listing snippets and return them from parse_job.
    """

    source = "trudnet"
    _BASE = "https://trud.net/"

    _CITY_ALIASES = {
        # Common UA cities as used on trud.net
        "kyiv": "kyev",
        "kiev": "kyev",
        "киев": "kyev",
        "київ": "kyev",
        "kharkiv": "harkov",
        "kharkov": "harkov",
        "харьков": "harkov",
        "харків": "harkov",
        "odesa": "odessa",
        "odessa": "odessa",
        "одесса": "odessa",
        "одеса": "odessa",
        "dnipro": "dnepropetrovsk",
        "dnepr": "dnepropetrovsk",
        "днепр": "dnepropetrovsk",
        "дніпро": "dnepropetrovsk",
        "zaporizhzhia": "zaporozhe",
        "zaporozhye": "zaporozhe",
        "zaporozhe": "zaporozhe",
        "запорожье": "zaporozhe",
        "запоріжжя": "zaporozhe",
        "vinnytsia": "vynnytsa",
        "vinnitsa": "vynnytsa",
        "винница": "vynnytsa",
        "вінниця": "vynnytsa",
        "zhytomyr": "zhitomir",
        "zhитомир": "zhitomir",
        "житомир": "zhitomir",
    }

    def __init__(self, fetcher, *, verbose: bool):
        super().__init__(fetcher, verbose=verbose)
        self._jobs_by_url: dict[str, Job] = {}

    @staticmethod
    def _query_terms(query: str) -> list[str]:
        q = (query or "").strip().lower()
        if not q:
            return []
        # split on whitespace/punctuation
        parts = re.split(r"[^\w\u0400-\u04FF]+", q)
        return [p for p in parts if len(p) >= 2]

    @classmethod
    def _city_slug(cls, city: str) -> str:
        c = (city or "").strip().lower()
        if not c:
            return "kyev"
        c = c.replace("'", "").replace("’", "").strip()
        return cls._CITY_ALIASES.get(c, "kyev")

    @classmethod
    def _list_url(cls, *, city: str, page: int) -> str:
        slug = cls._city_slug(city)
        base = f"{cls._BASE}rabota-{slug}/"
        if page <= 1:
            return base
        return f"{base}?pg={page}"

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

        terms = self._query_terms(query)
        urls: list[str] = []

        for page in range(1, max_pages + 1):
            if progress_cb:
                progress_cb(page, max_pages)

            page_url = self._list_url(city=city, page=page)
            r = await self._fetcher.get_text(page_url)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "lxml")

            # Heuristic: each item appears as H2 link with /away/<id>/
            for a in soup.select('a[href^="/away/"]'):
                href = (a.get("href") or "").strip()
                if not href:
                    continue

                title = a.get_text(" ", strip=True)
                if not title:
                    continue

                # Extract nearby snippet text (li / parent)
                li = a
                for _ in range(5):
                    if li is None:
                        break
                    if getattr(li, "name", "") == "li":
                        break
                    li = li.parent  # type: ignore[assignment]

                snippet = ""
                meta = ""
                if li is not None:
                    # typically: "City,сегодня" line is near the top
                    txt = li.get_text("\n", strip=True)
                    lines = [x.strip() for x in txt.split("\n") if x.strip()]
                    # remove title duplicates
                    lines = [x for x in lines if x != title]
                    if lines:
                        # first line often contains city/date
                        meta = lines[0]
                        snippet = "\n".join(lines[1:])

                combined = "\n".join([title, meta, snippet])
                combined_l = combined.lower()

                if terms and not all(t in combined_l for t in terms):
                    continue

                remote = is_remote(combined)
                if remote_only and not remote:
                    continue

                url = urljoin(self._BASE, href)
                if url in self._jobs_by_url:
                    continue

                emails = extract_emails(combined)
                phones = extract_phones(combined)

                published_at = ""
                location_text = ""
                if meta and "," in meta:
                    # e.g. "Одесса,сегодня" or "Харьков,3 дня назад"
                    parts = [p.strip() for p in meta.split(",", 1)]
                    location_text = parts[0]
                    published_at = parts[1] if len(parts) > 1 else ""
                else:
                    location_text = city
                    published_at = meta

                scraped_at = now_iso()
                job = Job(
                    source=self.source,
                    url=url,
                    title=title,
                    company="",
                    location=location_text or ("Remote" if remote else ""),
                    salary="",
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
