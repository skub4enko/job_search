from __future__ import annotations

from datetime import UTC, datetime

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


def now_iso(tz: str = "Europe/Kyiv") -> str:
    if ZoneInfo is None:
        return datetime.now(UTC).replace(microsecond=0).isoformat()
    try:
        return datetime.now(ZoneInfo(tz)).replace(microsecond=0).isoformat()
    except Exception:
        return datetime.now(UTC).replace(microsecond=0).isoformat()

