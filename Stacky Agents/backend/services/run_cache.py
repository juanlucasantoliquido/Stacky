"""V2.4 (plan 22) — Cache/dedup de runs CLI.

No pagar dos veces por el mismo trabajo. Un `run_fingerprint` determinista
identifica "el mismo run" = mismo prompt (sha, V1.1) + mismo modelo + mismo
contexto. Si ya existe un run `completed` con ese fingerprint dentro de la
ventana `STACKY_RUN_CACHE_DAYS`, el launch ofrece reusar ese resultado.

Reglas de oro:
- **Nunca** auto-skip: el operador decide (el launch solo devuelve un
  `cached_candidate`; sigue lanzando el run nuevo igual).
- Default OFF (`STACKY_RUN_CACHE_DAYS=0`) ⇒ comportamiento byte-idéntico al
  actual (lookup devuelve None sin tocar la DB).
- Sin `prompt_sha` (p.ej. copilot sin .agent.md) ⇒ sin fingerprint ⇒ sin dedup.
  Nunca inventamos identidad de run.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any


def _normalize_blocks(context_blocks: list[dict] | None) -> str:
    """Serialización canónica y estable de los context blocks.

    `sort_keys=True` neutraliza el orden de claves dentro de cada bloque; el
    orden de la lista SÍ importa (es contexto distinto). Si el contenido no es
    JSON-serializable, caemos a `repr` determinista (nunca crashear el sello).
    """
    if not context_blocks:
        return "[]"
    try:
        return json.dumps(
            context_blocks, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
    except (TypeError, ValueError):
        return repr(context_blocks)


def compute_fingerprint(
    *,
    prompt_sha: str | None,
    model: str | None,
    context_blocks: list[dict] | None,
) -> str | None:
    """sha256(prompt_sha + model + normalize(context_blocks)).

    Devuelve None si falta `prompt_sha` (sin identidad de prompt no hay dedup
    seguro: dos prompts distintos podrían colisionar).
    """
    if not prompt_sha:
        return None
    payload = "|".join(
        [str(prompt_sha), str(model or ""), _normalize_blocks(context_blocks)]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seal_into_metadata(
    metadata: dict[str, Any],
    *,
    prompt_sha: str | None,
    model: str | None,
    context_blocks: list[dict] | None,
) -> str | None:
    """Sella `metadata["run_fingerprint"]` (clave NUEVA) si se puede computar.

    Llamado por los runners CLI junto al sello de `prompt_sha` (V1.1). No-op si
    no hay fingerprint. Devuelve el fingerprint (o None) para conveniencia.
    """
    fp = compute_fingerprint(
        prompt_sha=prompt_sha, model=model, context_blocks=context_blocks
    )
    if fp:
        metadata["run_fingerprint"] = fp
    return fp


def find_cached_candidate(
    *,
    session,
    fingerprint: str | None,
    days: int,
    exclude_execution_id: int | None = None,
) -> int | None:
    """id de un run `completed` con el mismo fingerprint dentro de la ventana.

    `days <= 0` ⇒ feature apagada ⇒ None sin tocar la DB (retro-compat).
    Devuelve el más reciente; None si no hay hit.
    """
    if not fingerprint or not days or days <= 0:
        return None
    from models import AgentExecution

    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        session.query(AgentExecution)
        .filter(AgentExecution.status == "completed")
        .filter(AgentExecution.started_at >= cutoff)
        .order_by(AgentExecution.started_at.desc())
        .all()
    )
    for r in rows:
        if exclude_execution_id is not None and r.id == exclude_execution_id:
            continue
        if (r.metadata_dict or {}).get("run_fingerprint") == fingerprint:
            return r.id
    return None
