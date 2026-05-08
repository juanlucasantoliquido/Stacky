"""
resolution_cache.py — Caché episódica para resoluciones de precondiciones.

PROPÓSITO
---------
Evitar llamadas repetidas al LLM para las mismas precondiciones.

Cuando `precondition_parser.py` resuelve un término via LLM, el resultado
se guarda aquí indexado por fingerprint del texto original. En ejecuciones
futuras, el mismo texto se resuelve desde caché sin llamar al LLM.

DISEÑO
------
- Caché en disco: cache/resolution_cache.json
- Índice por fingerprint SHA-256 del texto normalizado (sin depender del texto exacto)
- TTL configurable (default: 7 días)
- Thread-safe para uso en pipeline

FORMATO (resolution_cache.json)
--------------------------------
{
  "version": "1.0",
  "entries": {
    "<fingerprint>": {
      "original_text": "...",
      "resolved_at": "ISO timestamp",
      "conditions": [ParsedCondition.to_dict(), ...]
    }
  }
}

API PÚBLICA
-----------
  get_cached(text) → list[dict] | None
  set_cached(text, conditions) → None
  invalidate(text) → None
  clear_expired() → int  (count de entradas eliminadas)
"""
from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.resolution_cache")

_TOOL_VERSION = "1.0.0"

_CACHE_PATH = Path(__file__).resolve().parent / "cache" / "resolution_cache.json"
_CACHE_TTL_DAYS = 7  # entradas más viejas que esto son consideradas expiradas

# Cache en memoria (cargado una vez por sesión)
_MEMORY_CACHE: Optional[dict] = None


# ── API pública ────────────────────────────────────────────────────────────────

def get_cached(text: str) -> Optional[list[dict]]:
    """
    Busca una resolución cacheada para el texto dado.

    Retorna list[dict] (condiciones) si existe y no expiró.
    Retorna None si no hay caché o expiró.
    """
    cache = _load()
    fp = _fingerprint(text)
    entry = cache.get("entries", {}).get(fp)
    if not entry:
        return None
    if _is_expired(entry.get("resolved_at", "")):
        logger.debug("resolution_cache: expired entry for '%s...'", text[:40])
        return None
    return entry.get("conditions", [])


def set_cached(text: str, conditions: list[dict]) -> None:
    """
    Guarda las condiciones resueltas para el texto dado.

    Persiste en disco inmediatamente.
    """
    cache = _load()
    fp = _fingerprint(text)
    cache.setdefault("entries", {})[fp] = {
        "original_text": text[:200],
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "conditions": conditions,
    }
    _write(cache)
    logger.debug("resolution_cache: cached resolution for '%s...'", text[:40])


def invalidate(text: str) -> None:
    """Elimina la entrada cacheada para el texto dado."""
    cache = _load()
    fp = _fingerprint(text)
    if fp in cache.get("entries", {}):
        del cache["entries"][fp]
        _write(cache)
        logger.info("resolution_cache: invalidated entry for '%s...'", text[:40])


def clear_expired() -> int:
    """
    Elimina todas las entradas expiradas del cache.
    Retorna la cantidad de entradas eliminadas.
    """
    cache = _load()
    entries = cache.get("entries", {})
    to_delete = [
        fp for fp, entry in entries.items()
        if _is_expired(entry.get("resolved_at", ""))
    ]
    for fp in to_delete:
        del entries[fp]
    if to_delete:
        _write(cache)
        logger.info("resolution_cache: cleared %d expired entries", len(to_delete))
    return len(to_delete)


# ── Internos ──────────────────────────────────────────────────────────────────

def _load() -> dict:
    global _MEMORY_CACHE
    if _MEMORY_CACHE is not None:
        return _MEMORY_CACHE

    if _CACHE_PATH.exists():
        try:
            raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            _MEMORY_CACHE = raw
            return _MEMORY_CACHE
        except Exception as exc:
            logger.warning("resolution_cache: could not read cache: %s", exc)

    _MEMORY_CACHE = {"version": "1.0", "entries": {}}
    return _MEMORY_CACHE


def _write(cache: dict) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("resolution_cache: could not write cache: %s", exc)


def _fingerprint(text: str) -> str:
    """SHA-256 del texto normalizado (minúsculas, sin tildes, sin espacios extra)."""
    nfkd = unicodedata.normalize("NFKD", text.lower().strip())
    normalized = " ".join("".join(c for c in nfkd if not unicodedata.combining(c)).split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _is_expired(resolved_at: str) -> bool:
    if not resolved_at:
        return True
    try:
        dt = datetime.fromisoformat(resolved_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) > timedelta(days=_CACHE_TTL_DAYS)
    except Exception:
        return True
