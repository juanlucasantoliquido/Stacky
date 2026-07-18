"""Plan 170 F2 — Cosecha de lecciones (flywheel).

Convierte una incidencia resuelta, una mutation lesson del 169 (outcome=='mejoro')
o un alta manual en una PROPUESTA `knowledge_note` del 167 (draft redactado por el
LLM local con degradación determinista, trazabilidad §4.4). El único camino
human-on-the-loop es `evolution_apply.maybe_auto_apply` del 167 — este módulo lo
LLAMA, nunca escribe la fuente de verdad de lecciones (KPI-3).

PII TOTAL (G15/C1): TODO insumo textual externo se enmascara con
`pii_masker.redact_irreversible` ANTES de entrar al draft, y el draft final
(title+body) se enmascara otra vez ANTES de `create_proposal` (defensa en
profundidad — una lección aprobada se inyecta a TODOS los prompts futuros).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from services import evolution_apply, evolution_store, knowledge_store as ks
from services import incident_store

logger = logging.getLogger(__name__)

_HARVEST_MAX_INPUT_CHARS = 24000   # cap del insumo total al redactor (~6k tokens)
_TITLE_MAX = 80
_BODY_MAX = 1200
_HARVEST_SYSTEM_PROMPT = (
    "Sos el destilador de lecciones de un sistema de agentes. Recibís el material de una "
    "incidencia RESUELTA (reporte + causa raíz verificada). Redactá UNA lección corta y "
    "accionable para que futuros agentes no repitan el problema. Respondé SOLO un JSON: "
    '{"title": "<max 80 chars>", "body": "<max 1200 chars: qué pasó, causa raíz, regla '
    'accionable para el futuro>", "tags": ["…"]}. Nada fuera del JSON. No inventes: usá '
    "solo lo que el material afirma."
)

_ROOT_CAUSE_RE = re.compile(
    r"CAUSA RAIZ\s*:?\s*(.+?)(?=\n\s*(?:ARCHIVOS MODIFICADOS|RESUMEN DEL FIX|$))",
    re.S | re.I,
)


class DuplicateSuspect(Exception):
    """La cosecha encontró una lección activa muy similar. `.similars`: list[dict]."""

    def __init__(self, similars: list[dict]):
        super().__init__("duplicate_suspect")
        self.similars = similars


def _noop_log(*_a, **_k) -> None:
    return None


# --------------------------------------------------------------------------- #
# PII + parsing
# --------------------------------------------------------------------------- #
def _mask(text: str | None) -> str:
    from services.pii_masker import redact_irreversible
    return redact_irreversible(text or "")


def _mask_draft(draft: dict) -> dict:
    """4b (G15/C1) — el draft final pasa por el masker antes de `create_proposal`."""
    return {
        "title": _mask(draft.get("title") or "")[:_TITLE_MAX],
        "body": _mask(draft.get("body") or "")[:_BODY_MAX],
        "tags": [str(t).strip() for t in (draft.get("tags") or []) if str(t).strip()][:6],
    }


def _parse_json_draft(text: str) -> dict | None:
    if not text:
        return None
    try:
        s = text.strip()
        if s.startswith("```"):
            s = s.strip("`")
        start = s.find("{")
        if start < 0:
            return None
        depth = 0
        end = -1
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end < 0:
            return None
        obj = json.loads(s[start:end])
        if not isinstance(obj, dict):
            return None
        title = str(obj.get("title") or "").strip()
        body = str(obj.get("body") or "").strip()
        if not title or not body:
            return None
        raw_tags = obj.get("tags")
        tags = ([str(t).strip() for t in raw_tags if str(t).strip()][:6]
                if isinstance(raw_tags, list) else [])
        return {"title": title[:_TITLE_MAX], "body": body[:_BODY_MAX], "tags": tags}
    except Exception:  # noqa: BLE001 — parse tolerante → fallback determinista
        return None


def _extract_root_cause(output: str | None) -> str | None:
    if not output:
        return None
    m = _ROOT_CAUSE_RE.search(output)
    if not m:
        return None
    rc = m.group(1).strip()
    return rc or None


# --------------------------------------------------------------------------- #
# Insumos tolerantes (G16)
# --------------------------------------------------------------------------- #
def _read_doc_masked(doc_path: str | None) -> str:
    if not doc_path:
        return ""
    try:
        p = Path(doc_path)
        if not p.exists():
            return ""
        raw = p.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""
    return _mask(raw)[: _HARVEST_MAX_INPUT_CHARS // 2]


def _find_dev_run(tracker_id) -> tuple[int | None, str | None]:
    if not tracker_id:
        return None, None
    try:
        ado_id = int(str(tracker_id).strip())
    except Exception:  # noqa: BLE001
        return None, None
    try:
        from db import session_scope
        from models import AgentExecution, Ticket
        with session_scope() as sess:
            row = (
                sess.query(AgentExecution)
                .join(Ticket, AgentExecution.ticket_id == Ticket.id)
                .filter(
                    Ticket.ado_id == ado_id,
                    AgentExecution.agent_type == "incident_dev",
                    AgentExecution.status == "completed",
                )
                .order_by(AgentExecution.id.desc())
                .first()
            )
            if row is None:
                return None, None
            return row.id, (row.output or "")
    except Exception:  # noqa: BLE001 — DB ausente/rota → sin run del dev
        return None, None


def _assemble_material(intake_masked: str, doc_masked: str,
                       root_cause: str | None) -> str:
    parts: list[str] = []
    if intake_masked:
        parts.append("REPORTE DE LA INCIDENCIA:\n" + intake_masked)
    if doc_masked:
        parts.append("DOCUMENTO DE LA INCIDENCIA:\n" + doc_masked)
    if root_cause:
        parts.append("CAUSA RAIZ VERIFICADA (del dev resolutor):\n" + root_cause)
    return "\n\n".join(parts)[:_HARVEST_MAX_INPUT_CHARS]


def _render_llm_draft(material: str) -> dict | None:
    try:
        from copilot_bridge import invoke_local_llm
        resp = invoke_local_llm(
            agent_type="knowledge_harvest", system=_HARVEST_SYSTEM_PROMPT,
            user=material, on_log=_noop_log,
        )
        return _parse_json_draft(getattr(resp, "text", None) or "")
    except Exception:  # noqa: BLE001 — sin endpoint/timeout/basura → plantilla
        return None


def _deterministic_draft(incident: dict, root_cause: str | None,
                         intake_masked: str) -> dict:
    iid = incident.get("id")
    title = ("Lección: " + (incident.get("title") or str(iid)))[:_TITLE_MAX]
    lines = [
        f"Incidencia {iid} ({incident.get('created_at')}).",
        "Reporte: " + (intake_masked or "")[:300],
    ]
    if root_cause:
        lines.append("Causa raíz verificada: " + root_cause[:500])
    lines.append("Regla: completá la regla accionable al aprobar esta lección.")
    return {"title": title, "body": "\n".join(lines), "tags": []}


# --------------------------------------------------------------------------- #
# Helpers de contrato
# --------------------------------------------------------------------------- #
def _find_eval_case_ref(source_ref: str) -> str | None:
    """Primer caso de eval con ese `source_ref` (168). Tolerante → None."""
    try:
        from evals import case_store
        for c in case_store.list_cases():
            if c.get("source_ref") == source_ref:
                return c.get("id")
    except Exception:  # noqa: BLE001
        return None
    return None


def _slug_from_aspect(aspect_key: str) -> str | None:
    if aspect_key and aspect_key.startswith("agent_prompts/"):
        slug = aspect_key.split("/", 1)[1].strip()
        return slug or None
    return None


def _load_optimizer_store():
    import importlib
    try:
        mod = importlib.import_module("services.evolution_optimizer_store")
        if mod is None:
            raise RuntimeError("optimizer_unavailable")
        return mod
    except RuntimeError:
        raise
    except Exception:  # noqa: BLE001 — Plan 169 ausente (import halted / None sentinel)
        raise RuntimeError("optimizer_unavailable")


# --------------------------------------------------------------------------- #
# Fuentes de cosecha
# --------------------------------------------------------------------------- #
def harvest_from_incident(incident_id: str, *, force: bool = False) -> dict:
    incident = incident_store.get_incident(incident_id)
    if incident is None:
        raise KeyError("incident_not_found")
    status = incident.get("status")
    if status != "publicada":
        raise ValueError(f"incident_not_harvestable:{status}")

    intake_masked = _mask(incident.get("text") or "")
    doc_masked = _read_doc_masked(incident.get("doc_path"))
    exec_id, dev_output = _find_dev_run(incident.get("tracker_id"))
    root_cause = _extract_root_cause(_mask(dev_output)) if dev_output else None

    material = _assemble_material(intake_masked, doc_masked, root_cause)
    llm_draft = _render_llm_draft(material)
    if llm_draft is not None:
        draft, marker = llm_draft, "harvest:llm_local"
    else:
        draft = _deterministic_draft(incident, root_cause, intake_masked)
        marker = "harvest:plantilla"
    draft = _mask_draft(draft)

    eval_case_id = _find_eval_case_ref(f"incident:{incident_id}")
    evidence = [f"incident:{incident_id}", marker]
    if exec_id is not None:
        evidence.append(f"execution:{exec_id}")
    if eval_case_id is not None:
        evidence.append(f"eval_case:{eval_case_id}")

    similars = ks.find_similar(draft["title"], draft["body"])
    if similars and not force:
        raise DuplicateSuspect(similars)
    scope = {"agent_types": [], "projects": [], "tags": draft.get("tags") or []}
    proposal = evolution_store.create_proposal(
        aspect_id="knowledge_rag", title=draft["title"],
        rationale="Lección cosechada de la incidencia " + incident_id,
        origin="agent", artifact_type="knowledge_note",
        proposed_content=draft["body"], evidence=evidence,
        initial_status="pending_review", actor="operator",
    )
    ks.upsert_meta(proposal["id"], title=draft["title"], scope=scope,
                   source={"kind": "incident", "ref": incident_id},
                   eval_case_id=eval_case_id)
    auto_applied = bool(evolution_apply.maybe_auto_apply(proposal))
    final = evolution_store.get_proposal(proposal["id"]) or proposal
    return {"proposal": final, "auto_applied": auto_applied, "duplicates": similars}


def harvest_from_optimizer_lesson(lesson_id: str, *, force: bool = False) -> dict:
    eos = _load_optimizer_store()
    lessons = eos.read_lessons_tail(limit=200)
    lesson = next((l for l in (lessons or []) if l.get("id") == lesson_id), None)
    if lesson is None:
        raise KeyError("optimizer_lesson_not_found")
    outcome = lesson.get("outcome")
    if outcome != "mejoro":
        raise ValueError(f"lesson_outcome_invalido:{outcome}")

    aspect_key = lesson.get("aspect_key") or ""
    title = ("Mejora verificada en " + aspect_key)[:_TITLE_MAX]
    body = (lesson.get("text") or "") + (
        f"\n(Delta de fitness verificado: +{lesson.get('delta')} en "
        f"{aspect_key}, corrida {lesson.get('run_id')}.)"
    )
    draft = _mask_draft({"title": title, "body": body, "tags": []})

    similars = ks.find_similar(draft["title"], draft["body"])
    if similars and not force:
        raise DuplicateSuspect(similars)
    slug = _slug_from_aspect(aspect_key)
    scope = {"agent_types": [slug] if slug else [], "projects": [], "tags": []}
    evidence = [
        f"optimizer_lesson:{lesson_id}",
        f"optimizer_run:{lesson.get('run_id')}",
        "harvest:promocion_determinista",
    ]
    proposal = evolution_store.create_proposal(
        aspect_id="knowledge_rag", title=draft["title"],
        rationale="Promoción de mejora verificada " + lesson_id,
        origin="optimizer", artifact_type="knowledge_note",
        proposed_content=draft["body"], evidence=evidence,
        initial_status="pending_review", actor="operator",
    )
    ks.upsert_meta(proposal["id"], title=draft["title"], scope=scope,
                   source={"kind": "optimizer_lesson", "ref": lesson_id})
    auto_applied = bool(evolution_apply.maybe_auto_apply(proposal))
    final = evolution_store.get_proposal(proposal["id"]) or proposal
    return {"proposal": final, "auto_applied": auto_applied, "duplicates": similars}


def harvest_manual(title: str, body: str, *, scope: dict | None = None,
                   force: bool = False) -> dict:
    if not title or not str(title).strip() or len(str(title)) > _TITLE_MAX:
        raise ValueError("invalid_payload:title")
    if not body or not str(body).strip() or len(str(body)) > _BODY_MAX:
        raise ValueError("invalid_payload:body")
    draft = _mask_draft({"title": str(title), "body": str(body), "tags": []})

    similars = ks.find_similar(draft["title"], draft["body"])
    if similars and not force:
        raise DuplicateSuspect(similars)
    proposal = evolution_store.create_proposal(
        aspect_id="knowledge_rag", title=draft["title"],
        rationale="Lección de alta manual",
        origin="manual", artifact_type="knowledge_note",
        proposed_content=draft["body"], evidence=["harvest:manual"],
        initial_status="pending_review", actor="operator",
    )
    ks.upsert_meta(proposal["id"], title=draft["title"],
                   scope=scope if scope else None,
                   source={"kind": "manual", "ref": None})
    auto_applied = bool(evolution_apply.maybe_auto_apply(proposal))
    final = evolution_store.get_proposal(proposal["id"]) or proposal
    return {"proposal": final, "auto_applied": auto_applied, "duplicates": similars}


# --------------------------------------------------------------------------- #
# F4 — lección → caso de eval borrador (reserva del 168 §8.3)
# --------------------------------------------------------------------------- #
def lesson_to_eval_case(lesson_id: str) -> dict:
    """Crea desde una lección activa un caso de eval BORRADOR (enabled=False) que la
    protege a futuro. El operador termina el check en el panel del 168 (HITL)."""
    from evals import case_store

    lesson = ks.get_lesson(lesson_id)
    if lesson is None:
        raise KeyError("lesson_not_found")
    if lesson.get("active") is False:
        raise ValueError("lesson_not_active")
    source_ref = f"lesson:{lesson_id}"
    for c in case_store.list_cases():
        if c.get("source_ref") == source_ref:
            raise ValueError("case_already_exists")

    agent_types = (lesson.get("scope") or {}).get("agent_types") or []
    if len(agent_types) == 1:
        aspect_key = f"agent_prompts/{agent_types[0]}"
        agent_type = agent_types[0]
    else:
        aspect_key = "knowledge_rag"
        agent_type = None

    case = case_store.create_case(
        aspect_key=aspect_key, agent_type=agent_type,
        subject="artifact", level="deterministic",
        title=("Protege lección: " + (lesson.get("title") or lesson_id))[:120],
        input={"kind": "artifact_text", "text": None, "golden_name": None},
        checks=[{
            "kind": "not_contains",
            "value": "COMPLETAR: anti-patron exacto que esta leccion prohibe",
            "case_sensitive": False,
        }],
        origin="lesson", enabled=False, source_ref=source_ref,
    )
    ks.upsert_meta(lesson_id, title=lesson.get("title") or lesson_id,
                   scope=lesson.get("scope"),
                   source=lesson.get("source"), eval_case_id=case["id"])
    return case
