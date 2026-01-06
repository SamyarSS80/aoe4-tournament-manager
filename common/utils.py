from __future__ import annotations

from typing import Any


def int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

def str_to_lower(v: Any, *, lower: bool = True) -> str:
    if v is None:
        return ""

    s = v if isinstance(v, str) else str(v)
    s = s.strip()
    if not s:
        return ""

    return s.lower() if lower else s

def normalize_str_value(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None