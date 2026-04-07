from __future__ import annotations

import asyncio
import hashlib
import os
import random
import threading
from dataclasses import dataclass
from pathlib import Path

import httpx


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status_code: int
    text: str
    from_cache: bool


class HttpFetcher:
    def __init__(self, *, cache_dir: Path, use_cache: bool, timeout_s: float, verbose: bool, pause_event: threading.Event | None = None, cancel_event: threading.Event | None = None):
        self._cache_dir = cache_dir
        self._use_cache = use_cache
        self._timeout = timeout_s
        self._verbose = verbose
        self._pause_event = pause_event
        self._cancel_event = cancel_event
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            ),
            "Accept-Language": "uk,ru-RU;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6",
        }
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_s),
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _cache_path(self, url: str) -> Path:
        return self._cache_dir / f"{_hash_url(url)}.html"

    async def _gate(self) -> None:
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise asyncio.CancelledError()
        while self._pause_event is not None and self._pause_event.is_set():
            await asyncio.sleep(0.2)
            if self._cancel_event is not None and self._cancel_event.is_set():
                raise asyncio.CancelledError()


    async def get_text(self, url: str, *, retries: int = 3) -> FetchResult:
        await self._gate()
        cache_path = self._cache_path(url)
        if self._use_cache and cache_path.exists():
            return FetchResult(
                url=url,
                status_code=200,
                text=cache_path.read_text(encoding="utf-8"),
                from_cache=True,
            )

        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                # Небольшой джиттер, чтобы не «долбить» сайт одинаково.
                if attempt > 0:
                    await asyncio.sleep(0.3 + random.random() * 0.7)
                await self._gate()
                await self._gate()
                r = await self._client.get(url)
                text = r.text
                if self._use_cache and r.status_code == 200:
                    tmp_path = cache_path.with_suffix(".tmp")
                    tmp_path.write_text(text, encoding="utf-8")
                    os.replace(tmp_path, cache_path)
                return FetchResult(url=url, status_code=r.status_code, text=text, from_cache=False)
            except Exception as e:
                last_exc = e

        if last_exc is None:
            raise RuntimeError("HTTP fetch failed without exception")
        raise last_exc
