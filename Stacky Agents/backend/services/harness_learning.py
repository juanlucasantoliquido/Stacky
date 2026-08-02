"""Plan 35 — Aprendizaje del arnés: patrones reutilizables.

Convierte las señales de verificación que hoy mueren al terminar cada run
(criterios incumplidos, precondiciones fallidas, repairs exitosos, modo de
fallo) en PATRONES persistentes, agregados por proyecto + agente + tipo de
ticket, que después se reinyectan como pista podable y se le muestran al
operador.

Rieles duros (§0 y §Principios del plan):
  - NO decide ni actúa: observa, agrega y propone. El operador manda.
  - El DESCARTE DEL OPERADOR ES DE POR VIDA: un patrón en "rejected" no vuelve
    a crearse ni a reactivarse por la cosecha automática (decisión (b)).
  - CERO tabla nueva y CERO cambios en `memory_store`: un patrón es una
    observación más, con un `scope` reservado que la allowlist `INJECT_SCOPES`
    deja fuera de la inyección de memoria de dominio por construcción.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace

from services import memory_store
from services.pr_review_sanitize import redact_secrets

# ── Constantes de dominio ────────────────────────────────────────────────────

# Scope reservado. 15 chars: entra en la columna String(20) de la observación.
# Queda FUERA de memory_store.INJECT_SCOPES ("project","team","global"), que es
# una ALLOWLIST: por eso un patrón jamás contamina la memoria de dominio.
HARNESS_PATTERN_SCOPE = "harness_pattern"

# `type` es obligatorio en upsert_by_topic_key (omitirlo da TypeError). "pattern"
# está en INJECTABLE_TYPES y NO en RESERVED_TYPES (los tipos del canal SYSTEM).
HARNESS_PATTERN_TYPE = "pattern"

PATTERN_STATUS_ACTIVE = "active"
# OJO: "dismissed" NO existe en memory_store.ALL_STATUSES. `set_status` no valida
# (asigna el string tal cual), así que usarlo habría metido un estado fuera de
# taxonomía, invisible para todo consumidor que itere ALL_STATUSES.
PATTERN_STATUS_DISMISSED = "rejected"

# Ventana de escaneo. Desvío D-1 declarado en §13 del plan: `list_observations`
# ordena por updated_at DESC y RECIÉN AHÍ aplica .limit(), o sea recorta por
# RECENCIA, no por confianza. Con el filtro de confianza en Python (decisión (a))
# un patrón bueno pero viejo puede caer fuera de la ventana. El costo es un falso
# NEGATIVO (una pista que no se inyecta), nunca un falso positivo, y el decay de
# F3 apunta en la misma dirección que la ventana.
_PATTERN_SCAN_LIMIT = 500

# Tope del fragmento legible del signal_key. El topic_key completo son 5 campos
# separados por "|" y va a una columna String(200).
_SIGNAL_KEY_TEXT_MAX = 60
_SIGNAL_KEY_HASH_LEN = 8

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class HarnessPattern:
    project: str
    agent_type: str   # "functional" | "technical" | "developer" | "qa" | "unknown"
    ticket_kind: str  # "bug" | "feature" | "task" | "unknown"
    signal_kind: str  # criterion_fail | verifier_fail | contract_fail
                      # | repair_success | run_failure
    signal_key: str   # id estable del fallo (normalizado + hash corto)
    remedy_hint: str  # texto corto redactado (puede ser "")
    occurrences: int  # DERIVADO de revision_count al leer; nunca se escribe a mano
    confidence: float # recalculado on-read (F3); la columna es informativa
    last_seen: str    # ISO (YYYY-MM-DD)


# ── Claves estables ──────────────────────────────────────────────────────────


def normalize_signal_key(raw: str) -> str:
    """Estabiliza y ACOTA la clave de una señal.

    Los criterios reales que trae `criteria_repair.unmet_before` llegan a ~250
    chars (medido en §3-bis del plan). Sin normalizar, la clave sería inestable
    (espacios, mayúsculas) y desbordaría el `topic_key`.

    Regla: minúsculas + colapsar whitespace + truncar, y anexar los primeros 8
    hex de un sha1 del texto normalizado COMPLETO, para que dos criterios con el
    mismo prefijo largo no colisionen. Determinista, sin deps.
    """
    text = _WS.sub(" ", (raw or "").strip().lower())
    if not text:
        return ""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:_SIGNAL_KEY_HASH_LEN]
    return f"{text[:_SIGNAL_KEY_TEXT_MAX]}#{digest}"


def pattern_topic_key(p: HarnessPattern) -> str:
    """Identidad del patrón. El store hace upsert por esta clave."""
    return "|".join(
        (
            p.project,
            p.agent_type,
            p.ticket_kind,
            p.signal_kind,
            normalize_signal_key(p.signal_key),
        )
    )


# ── Decisión (b): el descarte del operador es de POR VIDA ────────────────────


def is_dismissed_topic(project: str, topic_key: str) -> bool:
    """True si el operador ya descartó este patrón.

    `upsert_by_topic_key` pisa `status` y `confidence` INCONDICIONALMENTE (su
    único guard es no degradar active→draft). Sin este chequeo, una re-cosecha
    resucitaría un patrón descartado y el "descarte de por vida" que el plan
    promete sería una mentira de manual.

    El guard vive ACÁ y no en `memory_store`: `upsert_by_topic_key` es genérico y
    lo consumen otros servicios; cambiar su semántica para un solo caller
    rompería el contrato compartido.
    """
    if not project or not topic_key:
        return False
    try:
        rows = memory_store.list_observations(
            project=project,
            scope=HARNESS_PATTERN_SCOPE,
            status=PATTERN_STATUS_DISMISSED,
            limit=_PATTERN_SCAN_LIMIT,
        )
    except Exception:  # noqa: BLE001 — best-effort: ante duda NO se bloquea el alta
        return False
    return any((r.get("topic_key") or "") == topic_key for r in rows)


# ── Persistencia ─────────────────────────────────────────────────────────────


def persist_pattern(p: HarnessPattern) -> str:
    """Guarda (o refresca) un patrón. Devuelve el memory_id, o "" si no persistió.

    `occurrences` y `confidence` NO se serializan en el JSON: el primero se
    deriva de `revision_count` (que el store incrementa solo, de forma atómica) y
    el segundo se recalcula on-read.
    """
    if not (p.project or "").strip():
        return ""

    # redact_secrets es idempotente sobre texto limpio: se llama sin predicado
    # previo (no existe ningún `contains_secret` en el repo).
    safe = replace(
        p,
        project=p.project.strip(),
        remedy_hint=redact_secrets(p.remedy_hint or ""),
        signal_key=redact_secrets(p.signal_key or ""),
    )
    topic = pattern_topic_key(safe)

    if is_dismissed_topic(safe.project, topic):
        return ""

    payload = json.dumps(
        {
            "agent_type": safe.agent_type,
            "ticket_kind": safe.ticket_kind,
            "signal_kind": safe.signal_kind,
            "signal_key": safe.signal_key,
            "remedy_hint": safe.remedy_hint,
            "last_seen": safe.last_seen,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return memory_store.upsert_by_topic_key(
        project=safe.project,
        type=HARNESS_PATTERN_TYPE,
        title=safe.signal_key[:120] or "(sin clave)",
        content=payload,
        scope=HARNESS_PATTERN_SCOPE,
        topic_key=topic,
        status=PATTERN_STATUS_ACTIVE,
        confidence=safe.confidence,
        source_agent_type=safe.agent_type,
    )
