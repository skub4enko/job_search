from __future__ import annotations

import asyncio
import threading
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from job_search.http_client import HttpFetcher
from job_search.models import Job
from job_search.providers import get_providers


LogFn = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class RunConfig:
    query: str
    city: str
    remote_only: bool
    sources: list[str]
    max_pages: int
    limit: int
    cache_dir: Path
    use_cache: bool
    timeout_s: float
    concurrency: int
    verbose: bool
    log_fn: LogFn | None
    pause_event: threading.Event | None
    cancel_event: threading.Event | None


def _log(cfg: RunConfig, msg: str) -> None:
    if cfg.log_fn is not None:
        cfg.log_fn(msg)
        return
    print(msg, file=sys.stderr)



def _progress(cfg: RunConfig, msg: str) -> None:
    # Progress messages are primarily for GUI to show that work is ongoing.
    # We emit them when a log_fn is provided, or when verbose is enabled.
    if cfg.log_fn is not None:
        cfg.log_fn(f"[progress] {msg}")
        return
    if cfg.verbose:
        print(f"[progress] {msg}", file=sys.stderr)


async def _run_async(cfg: RunConfig) -> list[Job]:
    providers_map = get_providers()
    unknown = [s for s in cfg.sources if s not in providers_map]
    if unknown:
        raise ValueError(
            f"Неизвестные источники: {', '.join(unknown)}. Доступно: {', '.join(providers_map)}"
        )

    fetcher = HttpFetcher(
        cache_dir=cfg.cache_dir,
        use_cache=cfg.use_cache,
        timeout_s=cfg.timeout_s,
        verbose=cfg.verbose,
        pause_event=cfg.pause_event,
        cancel_event=cfg.cancel_event,
    )

    async def _gate() -> None:
        if cfg.cancel_event is not None and cfg.cancel_event.is_set():
            raise asyncio.CancelledError()
        while cfg.pause_event is not None and cfg.pause_event.is_set():
            await asyncio.sleep(0.2)
            if cfg.cancel_event is not None and cfg.cancel_event.is_set():
                raise asyncio.CancelledError()


    try:
        out: list[Job] = []
        src_total = len(cfg.sources)
        for src_i, source in enumerate(cfg.sources, start=1):
            await _gate()
            provider_cls = providers_map[source]
            provider = provider_cls(fetcher, verbose=cfg.verbose)

            # Stage: search
            _progress(cfg, f"{source} ({src_i}/{src_total}): searching")

            def on_page(page: int, total: int) -> None:
                _progress(cfg, f"{source} ({src_i}/{src_total}): search page {page}/{total}")

            if cfg.verbose:
                _log(cfg, f"[{source}] search...")

            await _gate()
            job_urls = await provider.search_job_urls(
                query=cfg.query,
                city=cfg.city,
                remote_only=cfg.remote_only,
                max_pages=cfg.max_pages,
                limit=cfg.limit,
                progress_cb=on_page,
            )

            if cfg.verbose:
                _log(cfg, f"[{source}] found urls={len(job_urls)}")

            if not job_urls:
                _progress(cfg, f"{source} ({src_i}/{src_total}): no results")
                continue

            total = len(job_urls)
            _progress(cfg, f"{source} ({src_i}/{src_total}): parsing {total} jobs")

            sem = asyncio.Semaphore(max(1, cfg.concurrency))

            async def parse_one(u: str) -> Job | None:
                async with sem:
                    try:
                        await _gate()
                        return await provider.parse_job(u, remote_only=cfg.remote_only, city=cfg.city)
                    except Exception as e:
                        if cfg.verbose:
                            _log(cfg, f"[{source}] parse failed: {u}: {e}")
                        return None

            tasks = [asyncio.create_task(parse_one(u)) for u in job_urls]
            ok = 0
            done = 0
            step = max(1, total // 10)
            for t in asyncio.as_completed(tasks):
                if cfg.cancel_event is not None and cfg.cancel_event.is_set():
                    for _t in tasks:
                        _t.cancel()
                    _progress(cfg, f"{source} ({src_i}/{src_total}): cancelled")
                    break
                j = await t
                done += 1
                if j is not None:
                    out.append(j)
                    ok += 1
                if done == 1 or done == total or (done % step == 0):
                    _progress(cfg, f"{source} ({src_i}/{src_total}): parsed {done}/{total} (ok={ok})")

            if cfg.verbose:
                _log(cfg, f"[{source}] parsed ok={ok}")
            _progress(cfg, f"{source} ({src_i}/{src_total}): done (ok={ok}/{total})")


        return out
    except asyncio.CancelledError:
        _progress(cfg, "cancelled")
        return out
    finally:
        await fetcher.aclose()


def run(
    *,
    query: str,
    city: str,
    remote_only: bool,
    sources: list[str],
    max_pages: int,
    limit: int,
    cache_dir: Path,
    use_cache: bool,
    timeout_s: float,
    concurrency: int,
    verbose: bool,
    log_fn: LogFn | None = None,
    pause_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
) -> list[Job]:
    cfg = RunConfig(
        query=query,
        city=city,
        remote_only=remote_only,
        sources=sources,
        max_pages=max_pages,
        limit=limit,
        cache_dir=cache_dir,
        use_cache=use_cache,
        timeout_s=timeout_s,
        concurrency=concurrency,
        verbose=verbose,
        log_fn=log_fn,
        pause_event=pause_event,
        cancel_event=cancel_event,
    )
    return asyncio.run(_run_async(cfg))
