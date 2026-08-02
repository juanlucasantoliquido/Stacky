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


# ── Lectura: confianza on-read + filtro EN PYTHON (decisión (a)) ─────────────


def compute_confidence(occurrences: int, days_since_last_seen: int) -> float:
    """Determinista, sin LLM, sin deps.

    base  = min(1.0, occurrences / 5.0)
    decay = 0.5 ** (days / 30)      # half-life 30 días

    Puntos de calibración: 1 ocurrencia hoy = 0.2 (NO se inyecta con el umbral
    0.5 por default); 3 ocurrencias hoy = 0.6 (se inyecta). Por eso el sistema
    arranca silencioso y se enciende solo cuando hay evidencia.
    """
    occ = max(0, int(occurrences or 0))
    days = max(0, int(days_since_last_seen or 0))
    base = min(1.0, occ / 5.0)
    decay = 0.5 ** (days / 30.0)
    return round(base * decay, 3)


def is_suppressed(pattern_status: str) -> bool:
    """True si el operador descartó el patrón."""
    return (pattern_status or "") == PATTERN_STATUS_DISMISSED


def _days_since(iso_ts: str | None) -> int:
    from datetime import datetime

    if not iso_ts:
        return 0
    try:
        seen = datetime.fromisoformat(str(iso_ts).replace("Z", ""))
    except Exception:  # noqa: BLE001
        return 0
    return max(0, (datetime.utcnow() - seen).days)


def list_patterns(
    project: str,
    *,
    agent_type: str | None = None,
    ticket_kind: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 50,
) -> list[HarnessPattern]:
    """Patrones activos del proyecto, ordenados por confianza descendente.

    Decisión (a) del operador — el filtro de confianza es EN PYTHON:
    `list_observations` no acepta ese filtro (su firma es project/status/scope/
    type/limit) y armar una query propia habría duplicado el motor de acceso del
    store. Se trae el conjunto YA ACOTADO por project+scope+status con UNA sola
    llamada y se filtra en memoria.

    Presupuesto del camino caliente (guardarraíl 11): 1 query + a lo sumo
    _PATTERN_SCAN_LIMIT deserializaciones. Nunca N queries, nunca sin límite.

    Desvío D-1: el .limit() se aplica DESPUÉS de ordenar por updated_at desc, o
    sea recorta por RECENCIA. Un patrón muy bueno pero viejo puede quedar fuera.
    """
    if not project:
        return []
    rows = memory_store.list_observations(
        project=project,
        scope=HARNESS_PATTERN_SCOPE,
        status=PATTERN_STATUS_ACTIVE,
        limit=_PATTERN_SCAN_LIMIT,
    )
    out: list[HarnessPattern] = []
    for r in rows:
        if is_suppressed(r.get("status") or ""):
            continue  # cinturón y tirantes: el status ya se filtró en la query
        try:
            data = json.loads(r.get("content") or "{}")
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, dict):
            continue
        if agent_type and data.get("agent_type") != agent_type:
            continue
        if ticket_kind and data.get("ticket_kind") != ticket_kind:
            continue
        occurrences = int(r.get("revision_count") or 1)
        conf = compute_confidence(occurrences, _days_since(r.get("updated_at")))
        if conf < min_confidence:
            continue
        out.append(
            HarnessPattern(
                project=r.get("project") or project,
                agent_type=str(data.get("agent_type") or "unknown"),
                ticket_kind=str(data.get("ticket_kind") or "unknown"),
                signal_kind=str(data.get("signal_kind") or ""),
                signal_key=str(data.get("signal_key") or ""),
                remedy_hint=str(data.get("remedy_hint") or ""),
                occurrences=occurrences,
                confidence=conf,
                last_seen=str(data.get("last_seen") or ""),
            )
        )
    out.sort(key=lambda p: (-p.confidence, -p.occurrences, p.signal_key))
    return out[: max(0, int(limit))]


# ── F1 — Cosecha pasiva post-run ─────────────────────────────────────────────

# Mapeo tipo del tracker -> ticket_kind. El tipo declarado por el tracker MANDA
# sobre cualquier heurística de título.
_WI_TYPE_KIND = {
    "bug": "bug", "defect": "bug", "incidencia": "bug", "incident": "bug",
    "issue": "bug",
    "feature": "feature", "epic": "feature", "epica": "feature",
    "user story": "feature", "userstory": "feature", "historia": "feature",
    "requirement": "feature",
    "task": "task", "tarea": "task", "subtask": "task",
}

_TITLE_BUG = ("error", "falla", "fallo", "bug", "no funciona", "incidencia",
              "excepcion", "excepción", "roto", "corrige", "corregir", "arreglar")
_TITLE_FEATURE = ("nueva", "nuevo", "agregar", "añadir", "anadir", "implementar",
                  "funcionalidad", "feature", "permitir", "incorporar")


def classify_ticket_kind(ticket_title: str, work_item_type: str | None) -> str:
    """Heurística barata stdlib -> "bug" | "feature" | "task" | "unknown". Sin LLM.

    OJO: el 2º parámetro es el WORK ITEM TYPE del tracker. `Ticket.type` NO
    EXISTE en el modelo — los campos reales son `work_item_type` (models.py) y
    `local_work_item_type`. Un getattr(ticket, "type", None) devuelve None
    SIEMPRE y EN SILENCIO, dejando ciega a esta función.
    """
    wt = (work_item_type or "").strip().lower()
    if wt:
        mapped = _WI_TYPE_KIND.get(wt)
        if mapped:
            return mapped
    title = (ticket_title or "").strip().lower()
    if not title:
        return "unknown"
    if any(w in title for w in _TITLE_BUG):
        return "bug"
    if any(w in title for w in _TITLE_FEATURE):
        return "feature"
    return "task"


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _extract_signals(md: dict) -> list[tuple[str, str, str]]:
    """(signal_kind, signal_key, remedy_hint) por cada señal de la metadata.

    SOLO lee claves OBSERVADAS en la calibración F1.0 (§3-bis del plan, fixture
    tests/fixtures/harness_metadata_sample.json). Escribir acá el nombre de una
    clave que no exista devuelve 0 patrones EN SILENCIO — el peor falso verde
    posible, porque toda la suite con mocks pasaría igual.

    Nunca lanza: la metadata de producción llega con shapes corruptos.
    """
    out: list[tuple[str, str, str]] = []
    if not isinstance(md, dict):
        return out

    # criteria_repair: {"attempted": bool, "unmet_before": [str], "recovered": bool|null}
    cr = _as_dict(md.get("criteria_repair"))
    unmet = cr.get("unmet_before")
    if isinstance(unmet, (list, tuple)):
        for item in unmet:
            text = str(item or "").strip()
            if text:
                out.append(("criterion_fail", text, ""))
    if cr.get("recovered") is True:
        out.append((
            "repair_success",
            "criteria_repair",
            "el pase correctivo de criterios recuperó el run",
        ))

    # precondition_failure: {"check": str, "detail": str}
    pf = _as_dict(md.get("precondition_failure"))
    check = str(pf.get("check") or "").strip()
    if check:
        out.append(("contract_fail", check, str(pf.get("detail") or "").strip()))

    # validation_playbook: {"status": str, "degraded_reason": str, ...}
    # OJO: el enum del productor es
    #   VALID_STATUSES = {"agent_provided", "enriched", "degraded", "disabled"}
    #   (services/validation_playbook.py)
    # y "ok" NO EXISTE en él. Una condición `status != "ok"` cosecha como fallo
    # TODOS los estados, incluido "enriched", que es el estado de ÉXITO — medido:
    # 15 filas "enriched" contra 6 "degraded". El único estado que significa
    # fallo es "degraded"; "disabled" es apagado, no fallo.
    vp = _as_dict(md.get("validation_playbook"))
    if str(vp.get("status") or "").strip() == "degraded":
        key = str(vp.get("degraded_reason") or "").strip() or "degraded"
        out.append(("verifier_fail", key, ""))

    # autocorrect: {"attempts": int, "max_retries": int, "last_action": str, ...}
    ac = _as_dict(md.get("autocorrect"))
    try:
        attempts = int(ac.get("attempts") or 0)
    except Exception:  # noqa: BLE001
        attempts = 0
    if attempts > 0 and str(ac.get("last_action") or "") == "ok":
        out.append((
            "repair_success",
            "autocorrect",
            f"la autocorrección resolvió el run en {attempts} intento(s)",
        ))

    # failure_kind: str — "crash" | "contract_failed"
    fk = md.get("failure_kind")
    if isinstance(fk, str) and fk.strip():
        out.append(("run_failure", fk.strip(), ""))

    return out


def harvest_from_execution(
    *,
    ticket_id: int,
    execution_id: int,
    final_status: str,
    agent_type: str | None = None,
    error: str | None = None,
    **kwargs,
) -> int:
    """Post-hook de cosecha. Devuelve el nº de patrones persistidos. Best-effort.

    Firma EXACTA que documenta `ticket_status.register_post_hook`:
      fn(*, ticket_id, execution_id, final_status, agent_type, error, **kwargs)
    El `**kwargs` es obligatorio: el chokepoint puede pasar claves adicionales.

    Seam: `on_execution_end` (3/3 runtimes), NO `finalize_run` (1/3 — sólo Codex
    CLI). Acá la metadata YA está persistida en la fila, a diferencia del
    `metadata_patch` de PostRunResult, que es un patch todavía sin fusionar.
    """
    from datetime import datetime

    from config import config as _cfg

    if not getattr(_cfg, "STACKY_HARNESS_LEARNING_HARVEST_ENABLED", True):
        return 0

    try:
        from db import session_scope
        from models import AgentExecution, Ticket

        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return 0
            md = row.metadata_dict or {}
            ticket = session.get(Ticket, ticket_id)
            # TODOS los escalares se capturan DENTRO de la sesión: afuera el
            # objeto queda detached y cualquier acceso da DetachedInstanceError.
            project = getattr(ticket, "stacky_project_name", "") or ""
            ticket_title = getattr(ticket, "title", "") or ""
            wi_type = (
                getattr(ticket, "work_item_type", None)
                or getattr(ticket, "local_work_item_type", None)
            )
    except Exception:  # noqa: BLE001
        return 0

    if not project:
        return 0

    kind = classify_ticket_kind(ticket_title, wi_type)
    today = datetime.utcnow().date().isoformat()
    n = 0
    for signal_kind, signal_key, remedy in _extract_signals(md):
        try:
            persisted = persist_pattern(
                HarnessPattern(
                    project=project,
                    agent_type=(agent_type or "unknown"),
                    ticket_kind=kind,
                    signal_kind=signal_kind,
                    signal_key=signal_key,
                    remedy_hint=remedy,
                    occurrences=1,
                    confidence=0.0,   # se recalcula on-read
                    last_seen=today,
                )
            )
        except Exception:  # noqa: BLE001
            continue
        if persisted:
            n += 1
    return n


def register(register_post_hook) -> None:
    """Cableado. Mismo idioma que services/epic_autopublish.register."""
    register_post_hook(harvest_from_execution)


# ── F2 — Reinyección como pista barata y podable ─────────────────────────────

# Clave "id" del dict de bloque. NO es "name": los bloques del motor son dicts,
# no objetos, y la prioridad NO es un campo del bloque — sale del mapa
# _BLOCK_PRIORITY de context_enrichment vía _block_priority(block).
HARNESS_PATTERN_BLOCK_ID = "harness-patterns"

_HINT_TITLE = "Fallos recurrentes en este tipo de ticket (pistas, no obligatorias)"
_HINT_LINE_MAX = 200


def build_pattern_hint_block(
    *,
    project: str,
    agent_type: str,
    ticket_title: str,
    work_item_type: str | None,
    max_patterns: int = 5,
    min_confidence: float = 0.5,
) -> dict | None:
    """Bloque dict listo para blocks.append(), o None si no hay nada que decir.

    Devolver None (y no un bloque vacío) es parte del presupuesto: sin patrones
    el costo adicional del camino caliente es CERO.
    """
    if not project:
        return None
    kind = classify_ticket_kind(ticket_title or "", work_item_type)
    pats = list_patterns(
        project,
        agent_type=agent_type,
        ticket_kind=kind,
        min_confidence=min_confidence,
        limit=max(0, int(max_patterns or 0)),
    )
    if not pats:
        return None

    lineas = []
    for p in pats:
        texto = f"- [{p.signal_kind}] {p.signal_key}"
        if p.remedy_hint:
            texto += f" — remedio que funcionó: {p.remedy_hint}"
        texto += f" (visto {p.occurrences}x)"
        lineas.append(texto[:_HINT_LINE_MAX])

    return {
        "kind": "text",
        "id": HARNESS_PATTERN_BLOCK_ID,
        "title": _HINT_TITLE,
        "content": (
            "Esto ya falló antes en este proyecto para este tipo de ticket. Son "
            "PISTAS, no requisitos: si el caso actual no aplica, ignoralas.\n"
            + "\n".join(lineas)
        ),
    }
