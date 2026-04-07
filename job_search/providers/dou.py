from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from job_search.extract import extract_emails, extract_phones, is_remote
from job_search.models import Job
from job_search.providers.base import Provider
from job_search.timeutil import now_iso


class DOUProvider(Provider):
    source = "dou"
    _FEED_BASE = "https://jobs.dou.ua/vacancies/feeds/"

    def __init__(self, fetcher, *, verbose: bool):
        super().__init__(fetcher, verbose=verbose)
        self._rss_fallback: dict[str, tuple[str, str]] = {}

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
        # DOU даёт RSS, который удобно парсить и он уже отсортирован по свежести.
        q = quote_plus(query)
        feed_url = f"{self._FEED_BASE}?search={q}"
        if remote_only:
            # На сайте remote-фильтр включается параметром remote=
            feed_url += "&remote="

        if progress_cb:
            progress_cb(1, 1)

        r = await self._fetcher.get_text(feed_url)
        if r.status_code != 200:
            if self._verbose:
                import sys
                print(f"[{self.source}] status={r.status_code} url={feed_url}", file=sys.stderr)
            return []

        urls: list[str] = []
        try:
            root = ET.fromstring(r.text)
        except Exception:
            return []

        for item in _find_items(root):
            link = _child_text(item, "link").strip()
            title = _child_text(item, "title").strip()
            pub = _child_text(item, "pubDate").strip()
            if link:
                urls.append(link)
                if title or pub:
                    self._rss_fallback[link] = (title, pub)
            if len(urls) >= limit:
                break

        return urls

    async def parse_job(self, url: str, *, remote_only: bool, city: str) -> Job | None:
        r = await self._fetcher.get_text(url)
        if r.status_code != 200:
            if self._verbose:
                import sys
                print(f"[{self.source}] status={r.status_code} url={feed_url}", file=sys.stderr)
            return None

        soup = BeautifulSoup(r.text, "lxml")
        page_text = soup.get_text("\n", strip=True)

        h1 = soup.select_one("h1")
        title = h1.get_text(strip=True) if h1 else ""

        company = ""
        for sel in (
            ".b-vacancy-head a[href*='/companies/']",
            ".b-vacancy-head a[href*='/company/']",
            "a.company",
            ".b-company a",
            ".b-vacancy-head__info a",
        ):
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                company = el.get_text(strip=True)
                break

        location = ""
        for sel in (
            ".place",
            ".b-vacancy-head .place",
            ".b-vacancy-head__geo",
            ".b-vacancy-head__info .place",
        ):
            el = soup.select_one(sel)
            if el and el.get_text(" ", strip=True):
                location = el.get_text(" ", strip=True)
                break

        salary = ""
        # На DOU зарплата часто в заголовке карточки/подзаголовке.
        m = re.search(r"(\$\s*\d[\d\s]*|\d[\d\s]*\s*(?:грн|uah|₴)|€\s*\d[\d\s]*)", page_text, re.IGNORECASE)
        if m:
            salary = m.group(1).strip()

        published_at = ""
        time_el = soup.select_one("time")
        if time_el:
            dt = (time_el.get("datetime") or "").strip()
            published_at = dt or time_el.get_text(strip=True)

        if not published_at:
            pub = self._rss_fallback.get(url, ("", ""))[1]
            published_at = pub

        remote = is_remote(page_text) or ("??????" in location.lower()) or ("remote" in title.lower())
        if remote_only and not remote:
            if self._verbose:
                import sys
                print(f"[{self.source}] skip non-remote url={url}", file=sys.stderr)
            return None

        emails = extract_emails(page_text)
        phones = extract_phones(page_text)

        description = ""
        desc_el = soup.select_one(".b-vacancy")
        if desc_el:
            description = desc_el.get_text("\n", strip=True)

        if not title:
            # фоллбек из RSS title: "Role в Company ..."
            rss_title = self._rss_fallback.get(url, ("", ""))[0]
            title = rss_title

        if not title:
            return None

        if not company:
            rss_title = self._rss_fallback.get(url, ("", ""))[0]
            company = _company_from_rss_title(rss_title)

        scraped_at = now_iso()
        return Job(
            source=self.source,
            url=url,
            title=title,
            company=company,
            location=location or ("Віддалено" if remote else ""),
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


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_items(root: ET.Element):
    for el in root.iter():
        if _strip_ns(el.tag) == "item":
            yield el


def _child_text(parent: ET.Element, name: str) -> str:
    for ch in list(parent):
        if _strip_ns(ch.tag) == name and ch.text:
            return ch.text
    return ""


def _company_from_rss_title(title: str) -> str:
    # Часто: "Role в Company ..."
    m = re.search(r"\sв\s+([^\s].+)$", title)
    if not m:
        return ""
    tail = m.group(1)
    # иногда дальше идут города/зарплата, отрежем по первому "(" или "віддалено"
    tail = re.split(r"\(|віддалено|\$|€|\d", tail, maxsplit=1)[0]
    return tail.strip(" \u00a0—-")
