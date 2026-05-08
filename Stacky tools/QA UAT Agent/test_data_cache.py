"""
test_data_cache.py — Resolved test data cache for QA UAT Agent.

Stores pre-resolved test data (IDs, names, etc.) so QA UAT does NOT need
to navigate the UI to find test data on every run.

Cache entry:
    {
        "field": "cliente_valido",
        "value": {"id": "123", "nombre": "Cliente QA"},
        "cached_at": "2026-05-07T10:00:00",
        "valid_until": "2026-05-07T18:00:00",
        "source": "db_query",
        "notes": ""
    }

TTL: QA_UAT_DATA_CACHE_TTL_HOURS (default: 8 hours).

By convention, entries that expire are NOT returned — the caller must
re-resolve them (via DB, precondition_checker, or manual entry).

Usage:
    from test_data_cache import get_data, store_data

    value = get_data("cliente_valido")
    if value is None:
        # resolve it, then...
        store_data("cliente_valido", {"id": "123", "nombre": "Cliente QA"}, source="db_query")

CLI:
    python test_data_cache.py --show
    python test_data_cache.py --clear
    python test_data_cache.py --clear-expired
    python test_data_cache.py --get cliente_valido
    python test_data_cache.py --set cliente_valido '{"id": "123"}' --source manual
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("stacky.qa_uat.test_data_cache")

_CACHE_DIR = Path(__file__).parent / "test_data_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_TTL_HOURS = 8


def _ttl_hours() -> int:
    return int(os.environ.get("QA_UAT_DATA_CACHE_TTL_HOURS", str(_DEFAULT_TTL_HOURS)))


def _entry_file(field: str) -> Path:
    # Sanitize field name for filesystem safety
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in field)
    return _CACHE_DIR / f"{safe}.json"


# ── Public API ─────────────────────────────────────────────────────────────────

def get_data(field: str) -> Optional[Any]:
    """Return cached value for `field` if it exists and hasn't expired.

    Returns None if not cached, expired, or QA_UAT_FORCE_RUN=true.
    """
    if os.environ.get("QA_UAT_FORCE_RUN", "").lower() in ("1", "true", "yes"):
        return None

    cache_file = _entry_file(field)
    if not cache_file.is_file():
        return None

    try:
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        valid_until = datetime.fromisoformat(entry.get("valid_until", "2000-01-01"))
        if datetime.utcnow() > valid_until:
            logger.debug("Data cache expired for field '%s'", field)
            cache_file.unlink(missing_ok=True)
            return None
        logger.debug("Data cache HIT for field '%s'", field)
        return entry.get("value")
    except Exception as exc:
        logger.warning("Could not read data cache for '%s': %s", field, exc)
        return None


def store_data(
    field: str,
    value: Any,
    source: str = "unknown",
    notes: str = "",
    ttl_hours: Optional[int] = None,
) -> None:
    """Store a resolved value in the data cache."""
    ttl = ttl_hours if ttl_hours is not None else _ttl_hours()
    now = datetime.utcnow()
    entry = {
        "field": field,
        "value": value,
        "cached_at": now.isoformat(),
        "valid_until": (now + timedelta(hours=ttl)).isoformat(),
        "source": source,
        "notes": notes,
    }
    try:
        _entry_file(field).write_text(
            json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.debug("Stored data cache for '%s' (ttl=%dh)", field, ttl)
    except Exception as exc:
        logger.warning("Could not write data cache for '%s': %s", field, exc)


def invalidate(field: str) -> bool:
    """Remove a single cached field. Returns True if removed."""
    f = _entry_file(field)
    if f.is_file():
        f.unlink()
        return True
    return False


def clear_expired() -> int:
    """Remove all expired entries. Returns count removed."""
    removed = 0
    now = datetime.utcnow()
    for f in _CACHE_DIR.glob("*.json"):
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            exp = datetime.fromisoformat(entry.get("valid_until", "2000-01-01"))
            if now > exp:
                f.unlink()
                removed += 1
        except Exception:
            pass
    return removed


def clear_all() -> int:
    """Remove all entries."""
    removed = 0
    for f in _CACHE_DIR.glob("*.json"):
        try:
            f.unlink()
            removed += 1
        except Exception:
            pass
    return removed


def list_entries() -> list:
    """Return all valid (non-expired) cache entries."""
    now = datetime.utcnow()
    entries = []
    for f in sorted(_CACHE_DIR.glob("*.json")):
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            exp = datetime.fromisoformat(entry.get("valid_until", "2000-01-01"))
            if now <= exp:
                entries.append(entry)
        except Exception:
            pass
    return entries


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="Test data cache manager")
    p.add_argument("--show", action="store_true")
    p.add_argument("--clear", action="store_true")
    p.add_argument("--clear-expired", dest="clear_expired", action="store_true")
    p.add_argument("--get", metavar="FIELD")
    p.add_argument("--set", metavar="FIELD")
    p.add_argument("--value", metavar="JSON", help="JSON value to store (with --set)")
    p.add_argument("--source", default="manual")
    args = p.parse_args()

    if args.show:
        entries = list_entries()
        print(json.dumps({"ok": True, "count": len(entries), "entries": entries},
                         ensure_ascii=False, indent=2))
    elif args.clear:
        n = clear_all()
        print(json.dumps({"ok": True, "cleared": n}))
    elif args.clear_expired:
        n = clear_expired()
        print(json.dumps({"ok": True, "cleared_expired": n}))
    elif args.get:
        val = get_data(args.get)
        print(json.dumps({"ok": val is not None, "field": args.get, "value": val},
                         ensure_ascii=False, indent=2))
    elif args.set:
        if not args.value:
            print(json.dumps({"ok": False, "error": "--value is required with --set"}))
            sys.exit(1)
        try:
            val = json.loads(args.value)
        except json.JSONDecodeError as exc:
            print(json.dumps({"ok": False, "error": f"Invalid JSON: {exc}"}))
            sys.exit(1)
        store_data(args.set, val, source=args.source)
        print(json.dumps({"ok": True, "field": args.set}))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
