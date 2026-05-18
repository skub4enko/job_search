from __future__ import annotations

import asyncio
import errno
import hashlib
import os
import random
import socket
import threading
import time
import sys
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
    def __init__(
        self,
        *,
        cache_dir: Path,
        use_cache: bool,
        timeout_s: float,
        verbose: bool,
        pause_event: threading.Event | None = None,
        cancel_event: threading.Event | None = None,
    ):
        self._cache_dir = cache_dir
        self._use_cache = use_cache
        self._timeout = timeout_s
        self._verbose = verbose
        self._pause_event = pause_event
        self._cancel_event = cancel_event
        self._offline_notice_at: float | None = None

        if self._use_cache:
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

    async def gate(self) -> None:
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise asyncio.CancelledError()
        while self._pause_event is not None and self._pause_event.is_set():
            await asyncio.sleep(0.2)
            if self._cancel_event is not None and self._cancel_event.is_set():
                raise asyncio.CancelledError()

    def _is_offline_exc(self, e: Exception) -> bool:
        # Typical offline cases on Windows: socket.gaierror(errno=11001), WinError 10060/10051/10054,
        # or httpx request/connect errors wrapping those.
        if isinstance(e, socket.gaierror):
            return True
        if isinstance(e, (httpx.ConnectError, httpx.NetworkError, httpx.ReadError, httpx.WriteError)):
            return True
        if isinstance(e, httpx.TimeoutException):
            # timeouts могут быть и при проблемах у сайта, но для UX лучше считать это сетевой проблемой
            return True

        err = getattr(e, "errno", None)
        if err in (errno.EHOSTUNREACH, errno.ENETUNREACH):
            return True

        # Windows WSA errors often sit in args or __cause__
        cause = getattr(e, "__cause__", None)
        if isinstance(cause, Exception) and self._is_offline_exc(cause):
            return True

        try:
            args_text = " ".join(str(a) for a in getattr(e, "args", ()) or ())
        except Exception:
            args_text = ""
        for token in ("11001", "10060", "10051", "10054"):
            if token in args_text:
                return True
        return False

    def is_offline_error(self, e: Exception) -> bool:
        return self._is_offline_exc(e)

    async def wait_for_internet(self) -> None:
        # Gate respects pause/cancel from GUI.
        await self.gate()

        def _probe() -> bool:
            # Use raw socket to avoid DNS (DNS might be exactly what is failing).
            def _try_connect(host: str, port: int) -> bool:
                try:
                    with socket.create_connection((host, port), timeout=2.0):
                        return True
                except OSError:
                    return False

            # A couple of well-known anycast DNS servers.
            return _try_connect("1.1.1.1", 53) or _try_connect("8.8.8.8", 53)

        backoff_s = 1.0
        while True:
            await self.gate()
            ok = await asyncio.to_thread(_probe)

            if ok:
                if self._offline_notice_at is not None:
                    print("[net] интернет снова доступен, продолжаю...", file=sys.stderr, flush=True)
                self._offline_notice_at = None
                return

            now = time.time()
            if self._offline_notice_at is None or (now - self._offline_notice_at) > 15:
                self._offline_notice_at = now
                print("[net] нет интернета, жду восстановления...", file=sys.stderr, flush=True)

            await asyncio.sleep(backoff_s)
            backoff_s = min(10.0, backoff_s * 1.5)

    async def get_text(self, url: str, *, retries: int = 3) -> FetchResult:
        await self.gate()

        cache_path = self._cache_path(url)
        if self._use_cache and cache_path.exists():
            return FetchResult(
                url=url,
                status_code=200,
                text=cache_path.read_text(encoding="utf-8"),
                from_cache=True,
            )

        last_exc: Exception | None = None
        attempt = 0
        max_attempts = max(1, retries)
        while attempt < max_attempts:
            try:
                if attempt > 0:
                    await asyncio.sleep(0.3 + random.random() * 0.7)
                await self.gate()

                r = await self._client.get(url)
                text = r.text
                if self._use_cache and r.status_code == 200:
                    tmp_path = cache_path.with_suffix(".tmp")
                    tmp_path.write_text(text, encoding="utf-8")
                    os.replace(tmp_path, cache_path)
                return FetchResult(url=url, status_code=r.status_code, text=text, from_cache=False)
            except Exception as e:
                last_exc = e
                if self._is_offline_exc(e):
                    # Pause until connection is back, then retry the same URL without consuming attempts.
                    await self.wait_for_internet()
                    continue
                attempt += 1

        if last_exc is None:
            raise RuntimeError("HTTP fetch failed without exception")
        raise last_exc
