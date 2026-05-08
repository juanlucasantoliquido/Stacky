"""
FA-31 — Output cache por hash.

Si dos operadores corren el mismo agente con contexto idéntico,
el segundo recibe el output desde cache (sin segunda llamada al LLM).

El hash combina:
- agent_type
- versión del system prompt (para invalidar al cambiar prompt)
- input_context normalizado (sin orden de keys, sin whitespace extra)

Implementación: tabla `output_cache` (creada al startup vía init_db).
La integración con `agent_runner` está en `_check_cache` y `_store_cache`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from db import Base, session_scope


# ---------------------------------------------------------------------------
# Modelo de cache (auto-creado por init_db al importar este módulo desde app.py)
# ---------------------------------------------------------------------------

class OutputCache(Base):
    __tablename__ = "output_cache"

    id = Column(Integer, primary_key=True)
    cache_key = Column(String(64), unique=True, nullable=False)
    agent_type = Column(String(20), nullable=False)
    output = Column(Text, nullable=False)
    output_format = Column(String(20), default="markdown")
    metadata_json = Column(Text)
    contract_result_json = Column(Text)
    hits = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_hit_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_outputcache_agent", "agent_type"),)


# ---------------------------------------------------------------------------
# Hash determinístico
# ---------------------------------------------------------------------------

# Cuando subimos versión del system prompt, bumpeamos esto y los caches se invalidan solos.
PROMPT_VERSION = "v1"


def _normalize_blocks(blocks: list[dict]) -> list[dict]:
    """Quita campos volátiles (ids, sources con timestamps) para que dos contextos
    estructuralmente iguales hagan hash igual."""
    normalized = []
    for b in blocks:
        normalized.append({
            "kind": b.get("kind"),
            "title": (b.get("title") or "").strip(),
            "content": (b.get("content") or "").strip(),
            "items": [
                {"selected": bool(it.get("selected")), "label": (it.get("label") or "").strip()}
                for it in (b.get("items") or [])
            ] or None,
        })
    return normalized


def compute_key(*, agent_type: str, blocks: list[dict]) -> str:
    payload = {
        "agent": agent_type,
        "prompt_version": PROMPT_VERSION,
        "blocks": _normalize_blocks(blocks),
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Lookup / store
# ---------------------------------------------------------------------------

CACHE_TTL = timedelta(days=7)


def lookup(*, agent_type: str, blocks: list[dict]) -> dict | None:
    """Si hay hit fresco en cache, devuelve dict con output / metadata / contract_result.
    Si no hay o expiró, devuelve None."""
    key = compute_key(agent_type=agent_type, blocks=blocks)
    with session_scope() as session:
        row = session.query(OutputCache).filter_by(cache_key=key).first()
        if row is None:
            return None
        if datetime.utcnow() - row.created_at > CACHE_TTL:
            return None
        row.hits = (row.hits or 0) + 1
        row.last_hit_at = datetime.utcnow()
        return {
            "cache_key": key,
            "output": row.output,
            "output_format": row.output_format or "markdown",
            "metadata": json.loads(row.metadata_json) if row.metadata_json else {},
            "contract_result": json.loads(row.contract_result_json) if row.contract_result_json else None,
            "hits": row.hits,
        }


def store(
    *,
    agent_type: str,
    blocks: list[dict],
    output: str,
    output_format: str = "markdown",
    metadata: dict | None = None,
    contract_result: dict | None = None,
) -> str:
    """Persiste un output en cache. Devuelve la cache_key."""
    key = compute_key(agent_type=agent_type, blocks=blocks)
    with session_scope() as session:
        row = session.query(OutputCache).filter_by(cache_key=key).first()
        if row is None:
            row = OutputCache(cache_key=key, agent_type=agent_type)
            session.add(row)
        row.output = output
        row.output_format = output_format
        row.metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        row.contract_result_json = json.dumps(contract_result, ensure_ascii=False) if contract_result else None
        row.created_at = datetime.utcnow()
        row.last_hit_at = datetime.utcnow()
    return key


def stats() -> dict[str, Any]:
    """Para `/api/admin/cache/stats` futuro."""
    with session_scope() as session:
        total = session.query(OutputCache).count()
        total_hits = session.query(OutputCache).with_entities(OutputCache.hits).all()
        hits_sum = sum(h or 0 for (h,) in total_hits)
        return {"entries": total, "total_hits": hits_sum}
