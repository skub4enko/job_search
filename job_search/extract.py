from __future__ import annotations

import re


_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Мягкий паттерн для UA телефонов: +380.. или 0.. с разделителями
_PHONE_RE = re.compile(
    r"(?:\+?3?8?0|0)"  # +380 / 380 / 0
    r"[\s\-\(]*\d{2}[\s\-\)]*"  # код оператора
    r"\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
)

_REMOTE_POSITIVE = re.compile(
    r"\b(віддалено|удал[её]нно|дистанц[іи]йно|remote|work\s*from\s*home|wfh)\b",
    re.IGNORECASE,
)
_REMOTE_STRONG = re.compile(
    r"\b(fully\s*remote|повн\w*\s+віддалено|100%\s*remote|full\s*remote)\b",
    re.IGNORECASE,
)
_REMOTE_DENY = re.compile(
    r"\b(не\s+віддалено|не\s+удал[её]нно|без\s+віддален\w*)\b",
    re.IGNORECASE,
)

# Гибрид/onsite — явный сигнал, что это не remote-only
_REMOTE_NEGATIVE = re.compile(r"\b(гібрид|hybrid|on\-site|onsite)\b", re.IGNORECASE)


def extract_emails(text: str) -> list[str]:
    if not text:
        return []
    emails = [e.lower() for e in _EMAIL_RE.findall(text)]
    return _uniq(emails)


def extract_phones(text: str) -> list[str]:
    if not text:
        return []
    phones = []
    for raw in _PHONE_RE.findall(text):
        normalized = _normalize_phone(raw)
        if normalized:
            phones.append(normalized)
    return _uniq(phones)


def is_remote(text: str) -> bool:
    if not text:
        return False
    if _REMOTE_DENY.search(text):
        return False
    if _REMOTE_STRONG.search(text):
        return True
    if not _REMOTE_POSITIVE.search(text):
        return False
    if _REMOTE_NEGATIVE.search(text):
        return False
    return True


def _normalize_phone(phone: str) -> str | None:
    digits = re.sub(r"\D+", "", phone)
    if not digits:
        return None

    # 0XXXXXXXXX (10 цифр) -> +38...
    if len(digits) == 10 and digits.startswith("0"):
        return "+38" + digits

    # 380XXXXXXXXX (12 цифр) -> +380...
    if len(digits) == 12 and digits.startswith("380"):
        return "+" + digits

    if len(digits) in {11, 12, 13}:
        if digits.startswith("380"):
            return "+" + digits
        if digits.startswith("38") and len(digits) == 11:
            return "+" + digits

    return None


def _uniq(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out
