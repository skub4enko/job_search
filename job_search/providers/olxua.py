from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from job_search.extract import extract_emails, extract_phones, is_remote
from job_search.models import Job
from job_search.providers.base import Provider
from job_search.timeutil import now_iso


class OLXUAProvider(Provider):
    source = "olxua"
    _BASE = "https://www.olx.ua/"

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
        # OLX работа: /uk/rabota/q-<query>/ + пагинация ?page=N
        # Для remote-only подмешиваем 'віддалено' в запрос.
        q_text = f"{query} віддалено" if remote_only else query
        slug = _to_q_slug(q_text)
        base_url = f"{self._BASE}uk/rabota/q-{slug}/"

        urls: list[str] = []
        for page in range(1, max_pages + 1):
            if progress_cb:
                progress_cb(page, max_pages)
            page_url = base_url if page == 1 else f"{base_url}?page={page}"
            r = await self._fetcher.get_text(page_url)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "lxml")

            for a in soup.select("a[href]"):
                href = (a.get("href") or "").strip()
                if not href:
                    continue

                # объявления в разделе работа обычно: /uk/obyavlenie/rabota/...<ID>.html
                if re.search(r"/uk/obyavlenie/rabota/[^\s]+\.html", href):
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
        # OLX: продавец/автор объявления
        seller = soup.select_one('[data-testid="user-profile-link"], a[href*="/d/uk/oferty/"]')
        if seller:
            company = seller.get_text(strip=True)

        location = ""
        loc = soup.select_one('[data-testid="location-date"], [data-testid="location"]')
        if loc:
            location = loc.get_text(" ", strip=True)

        salary = ""
        price = soup.select_one('[data-testid="ad-price-container"], [data-testid="ad-price"], .css-10b0gli')
        if price:
            salary = price.get_text(" ", strip=True)

        published_at = ""
        # OLX часто показывает: "Опубліковано ..." / "Сьогодні о ..."
        m = re.search(r"\b(Сьогодні|Вчора|\d{2}\.\d{2}\.\d{4})\b", page_text)
        if m:
            published_at = m.group(1)

        description = ""
        desc_el = soup.select_one('[data-testid="ad_description"], #textContent, [class*="description"]')
        if desc_el:
            description = desc_el.get_text("\n", strip=True)

        combined = "\n".join([title, company, location, salary, description, page_text])
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


def _to_q_slug(text: str) -> str:
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
