from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from job_search.http_client import HttpFetcher
from job_search.models import Job


class Provider(ABC):
    source: str

    def __init__(self, fetcher: HttpFetcher, *, verbose: bool):
        self._fetcher = fetcher
        self._verbose = verbose

    @abstractmethod
    async def search_job_urls(
        self,
        *,
        query: str,
        city: str,
        remote_only: bool,
        max_pages: int,
        limit: int,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def parse_job(self, url: str, *, remote_only: bool, city: str) -> Job | None:
        raise NotImplementedError
