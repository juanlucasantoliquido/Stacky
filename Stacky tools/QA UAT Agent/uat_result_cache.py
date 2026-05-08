"""
uat_result_cache.py — Execution result cache for QA UAT Agent.

Avoids re-running identical UAT scenarios when nothing has changed.

Cache key (SHA-256 of concatenation):
    ticket_id + scenario_id + playbook_id + base_url + build_id + test_data_hash

Cache entry:
    {
        "key": "<sha256>",
        "ticket_id": 70,
        "scenario_id": "P01",
        "playbook_id": "agenda_busqueda_cliente",
        "verdict": "PASS",
        "cached_at": "2026-05-07T10:00:00",
        "expires_at": "2026-05-07T18:00:00",
        "duration_ms": 18400,
        "base_url": "http://localhost:35017/AgendaWeb/"
    }

TTL: QA_UAT_RESULT_CACHE_TTL_HOURS (default: 8 hours).

Usage:
    from uat_result_cache import get_cached_result, store_result

    cached = get_cached_result(key_params)
    if cached:
        return {"verdict": "SKIPPED_CACHED_PASS", **cached}

    # ... run test ...
    store_result(key_params, verdict="PASS", duration_ms=18000)

CLI:
    python uat_result_cache.py --show            # list all valid cache entries
    python uat_result_cache.py --clear           # purge all entries
    python uat_result_cache.py --clear-expired   # purge only expired entries
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.result_cache")

_CACHE_DIR = Path(__file__).parent / "uat_result_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache entry TTL — configurable via env var.
_DEFAULT_TTL_HOURS = 8


def _ttl_hours() -> int:
    return int(os.environ.get("QA_UAT_RESULT_CACHE_TTL_HOURS", str(_DEFAULT_TTL_HOURS)))


# ── Public API ─────────────────────────────────────────────────────────────────

def build_key(
    ticket_id,
    scenario_id: str,
    playbook_id: str = "",
    base_url: str = "",
    build_id: str = "",
    test_data_hash: str = "",
) -> str:
    """Build a deterministic cache key from execution parameters."""
    raw = "|".join([
        str(ticket_id),
        scenario_id,
        playbook_id,
        (base_url or os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")),
        build_id,
        test_data_hash,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def get_cached_result(
    ticket_id,
    scenario_id: str,
    playbook_id: str = "",
    base_url: str = "",
    build_id: str = "",
    test_data_hash: str = "",
) -> Optional[dict]:
    """Return a cached result if one exists and has not expired.

    Returns None if cache is disabled (QA_UAT_FORCE_RUN=true), miss, or expired.
    """
    # Respect force-run override
    if os.environ.get("QA_UAT_FORCE_RUN", "").lower() in ("1", "true", "yes"):
        logger.debug("QA_UAT_FORCE_RUN=true — bypassing result cache")
        return None

    key = build_key(ticket_id, scenario_id, playbook_id, base_url, build_id, test_data_hash)
    cache_file = _CACHE_DIR / f"{key}.json"
    if not cache_file.is_file():
        return None

    try:
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Check expiry
    expires_at_str = entry.get("expires_at")
    if not expires_at_str:
        return None
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.utcnow() > expires_at:
            logger.debug("Cache expired for %s/%s (key=%s)", ticket_id, scenario_id, key[:8])
            cache_file.unlink(missing_ok=True)
            return None
    except Exception:
        return None

    # Only return PASS hits — FAIL/BLOCKED should always re-run
    if entry.get("verdict") != "PASS":
        logger.debug("Cache miss (non-PASS verdict) for %s/%s", ticket_id, scenario_id)
        return None

    logger.info("Cache HIT for %s/%s (key=%s, verdict=PASS)", ticket_id, scenario_id, key[:8])
    return entry


def store_result(
    ticket_id,
    scenario_id: str,
    verdict: str,
    duration_ms: int,
    playbook_id: str = "",
    base_url: str = "",
    build_id: str = "",
    test_data_hash: str = "",
) -> None:
    """Persist a test result to the cache.

    Only PASS verdicts are cached (FAIL/BLOCKED always re-run).
    """
    if verdict != "PASS":
        logger.debug("Not caching non-PASS result (%s) for %s/%s", verdict, ticket_id, scenario_id)
        return

    key = build_key(ticket_id, scenario_id, playbook_id, base_url, build_id, test_data_hash)
    now = datetime.utcnow()
    entry = {
        "key": key,
        "ticket_id": ticket_id,
        "scenario_id": scenario_id,
        "playbook_id": playbook_id,
        "verdict": verdict,
        "cached_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=_ttl_hours())).isoformat(),
        "duration_ms": duration_ms,
        "base_url": base_url or os.environ.get("AGENDA_WEB_BASE_URL", ""),
    }
    cache_file = _CACHE_DIR / f"{key}.json"
    try:
        cache_file.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("Cached PASS for %s/%s (key=%s, ttl=%dh)",
                     ticket_id, scenario_id, key[:8], _ttl_hours())
    except Exception as exc:
        logger.warning("Could not write cache entry: %s", exc)


def clear_expired() -> int:
    """Remove expired cache entries. Returns count removed."""
    removed = 0
    now = datetime.utcnow()
    for f in _CACHE_DIR.glob("*.json"):
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            exp = datetime.fromisoformat(entry.get("expires_at", "2000-01-01"))
            if now > exp:
                f.unlink()
                removed += 1
        except Exception:
            pass
    return removed


def clear_all() -> int:
    """Remove all cache entries. Returns count removed."""
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
            exp = datetime.fromisoformat(entry.get("expires_at", "2000-01-01"))
            if now <= exp:
                entries.append(entry)
        except Exception:
            pass
    return entries


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    import sys
    p = argparse.ArgumentParser(description="UAT result cache manager")
    p.add_argument("--show", action="store_true", help="List all valid cache entries")
    p.add_argument("--clear", action="store_true", help="Clear all cache entries")
    p.add_argument("--clear-expired", dest="clear_expired", action="store_true",
                   help="Clear only expired entries")
    args = p.parse_args()

    if args.clear:
        n = clear_all()
        print(json.dumps({"ok": True, "cleared": n}))
    elif args.clear_expired:
        n = clear_expired()
        print(json.dumps({"ok": True, "cleared_expired": n}))
    elif args.show:
        entries = list_entries()
        print(json.dumps({"ok": True, "count": len(entries), "entries": entries},
                         ensure_ascii=False, indent=2))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
