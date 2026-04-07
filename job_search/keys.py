from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ApiKeys:
    jooble: str
    scrapeops: str


def load_api_keys(path: Path) -> ApiKeys:
    """Loads API keys from a free-form text file.

    Supported formats:
    - lines like: https://jooble.org - <APIKEY>
    - or any text that contains a UUID-like Jooble key
    - lines like: SCRAPEOPS_API_KEY=<key>
    """

    if not path.exists():
        return ApiKeys(jooble="", scrapeops="")

    text = path.read_text(encoding="utf-8", errors="ignore")

    jooble = _extract_jooble(text)
    scrapeops = _extract_scrapeops(text)

    return ApiKeys(jooble=jooble, scrapeops=scrapeops)


def _extract_jooble(text: str) -> str:
    # 1) explicit mapping lines
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if "jooble" in s.lower() and "http" in s.lower() and "-" in s:
            # take rhs after first '-'
            rhs = s.split("-", 1)[1].strip().strip('"')
            if rhs and _UUID_RE.search(rhs):
                return _UUID_RE.search(rhs).group(0)  # type: ignore[union-attr]
            if rhs:
                return rhs

    # 2) UUID in any text (matches Jooble keys we usually see)
    m = _UUID_RE.search(text)
    return m.group(0) if m else ""


def _extract_scrapeops(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.search(r"\bSCRAPEOPS_API_KEY\b\s*[:=\-]\s*(.+)$", s, re.IGNORECASE)
        if m:
            return m.group(1).strip().strip('"')
    return ""
