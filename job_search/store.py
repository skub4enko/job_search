from __future__ import annotations

import json
import re
from pathlib import Path

from job_search.timeutil import now_iso


def load_payload(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def merge_payload(existing: list[dict], fresh: list[dict]) -> list[dict]:
    now = now_iso()

    old_map: dict[str, dict] = {}
    for rec in existing:
        if isinstance(rec, dict):
            norm = _normalize_record(rec)
            k = _key(norm)
            if k:
                old_map[k] = norm

    fresh_map: dict[str, dict] = {}
    for rec in fresh:
        if isinstance(rec, dict):
            norm = _normalize_record(rec)
            k = _key(norm)
            if k:
                fresh_map[k] = norm

    out_map: dict[str, dict] = {}

    # Обновляем/добавляем свежие
    for k, new in fresh_map.items():
        old = old_map.get(k)
        if old is None:
            new.setdefault("first_seen_at", new.get("scraped_at") or now)
            new["last_seen_at"] = new.get("scraped_at") or now
            new["is_active"] = True
            out_map[k] = new
            continue

        merged = dict(old)
        for field in (
            "title",
            "company",
            "location",
            "salary",
            "published_at",
            "remote",
            "description",
        ):
            val = new.get(field)
            if isinstance(val, str) and val.strip():
                merged[field] = val
            elif isinstance(val, bool):
                merged[field] = val

        for field in ("emails", "phones"):
            val = new.get(field)
            if isinstance(val, list) and val:
                merged[field] = _uniq([str(x) for x in val if str(x).strip()])

        merged["scraped_at"] = new.get("scraped_at") or now
        merged["last_seen_at"] = new.get("scraped_at") or now
        merged.setdefault("first_seen_at", old.get("first_seen_at") or (new.get("scraped_at") or now))
        merged["is_active"] = True

        out_map[k] = _normalize_record(merged)

    # Те, кого не нашли в этом прогоне — помечаем как неактивные
    for k, old in old_map.items():
        if k in out_map:
            continue
        merged = dict(old)
        merged["is_active"] = False
        merged.setdefault("first_seen_at", old.get("first_seen_at") or old.get("scraped_at") or now)
        merged.setdefault("last_seen_at", old.get("last_seen_at") or old.get("scraped_at") or now)
        out_map[k] = _normalize_record(merged)

    out = list(out_map.values())
    out.sort(key=lambda r: (not bool(r.get("is_active")), str(r.get("last_seen_at", ""))), reverse=False)
    # Сделаем активные первыми, а внутри — по last_seen_at убыванию
    out_active = [r for r in out if r.get("is_active")]
    out_inactive = [r for r in out if not r.get("is_active")]
    out_active.sort(key=lambda r: str(r.get("last_seen_at", "")), reverse=True)
    out_inactive.sort(key=lambda r: str(r.get("last_seen_at", "")), reverse=True)
    return out_active + out_inactive


def _key(rec: dict) -> str:
    s = str(rec.get("source") or "").strip().lower()
    u = str(rec.get("url") or "").strip()
    return f"{s}:{u}" if s and u else ""


def _normalize_record(rec: dict) -> dict:
    out = dict(rec)

    # миграции старых полей
    if "location" not in out and "city" in out:
        out["location"] = out.get("city")

    for f in (
        "source",
        "url",
        "title",
        "company",
        "location",
        "salary",
        "published_at",
        "description",
        "scraped_at",
        "first_seen_at",
        "last_seen_at",
    ):
        if f in out and out[f] is None:
            out[f] = ""

    out.setdefault("emails", [])
    out.setdefault("phones", [])
    if not isinstance(out.get("emails"), list):
        out["emails"] = []
    if not isinstance(out.get("phones"), list):
        out["phones"] = []

    out.setdefault("remote", False)
    out["remote"] = bool(out.get("remote"))

    out.setdefault("is_active", True)
    out["is_active"] = bool(out.get("is_active"))

    if isinstance(out.get("published_at"), str):
        out["published_at"] = _sanitize_published_at(out["published_at"])

    out["emails"] = _uniq([str(x).strip().lower() for x in out["emails"] if str(x).strip()])
    out["phones"] = _uniq([str(x).strip() for x in out["phones"] if str(x).strip()])

    return out


def _sanitize_published_at(value: str) -> str:
    s = (value or "").replace("\u00a0", " ").replace("\r", " ").replace("\n", " ").strip()
    s = " ".join(s.split())
    if len(s) <= 80:
        return s

    # Prefer keeping a date-like fragment if possible.
    m = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[^\d\s]{3,20}\s+\d{4})", s)
    if m:
        return m.group(1).strip()

    return s[:80].rstrip()


def _uniq(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out
