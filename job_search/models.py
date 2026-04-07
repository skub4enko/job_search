from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Job:
    source: str
    url: str
    title: str
    company: str
    location: str
    salary: str
    published_at: str
    remote: bool
    emails: list[str]
    phones: list[str]
    description: str
    scraped_at: str
    first_seen_at: str
    last_seen_at: str
    is_active: bool
