"""
ADO Pipeline Inference — infiere el estado del pipeline de un ticket
usando ÚNICAMENTE datos de Azure DevOps (título, descripción, comentarios,
adjuntos de texto) + un LLM (modelo gratuito/barato: gpt-4o-mini por defecto).

NO depende de archivos locales. La misma consulta en cualquier máquina
con acceso al mismo proyecto ADO produce el mismo resultado.

Flujo:
  1. Fetch full ticket context from ADO (título + desc + comentarios + adjuntos)
  2. Construye prompt estructurado
  3. Llama al LLM via copilot_bridge.invoke()
  4. Parsea respuesta JSON
  5. Cachea resultado en BD local (SQLite) con TTL configurable

Modelo SQLAlchemy: PipelineInferenceCache (tabla pipeline_inference_cache)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from config import config
from db import Base, session_scope

logger = logging.getLogger("stacky_agents.pipeline_inference")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INFERENCE_MODEL = "gpt-4o-mini"   # modelo gratuito/barato por defecto
CACHE_TTL_MINUTES = 60             # re-inferir tras 1 hora
MAX_COMMENT_CHARS = 800            # truncar comentarios largos para no quemar tokens
MAX_COMMENTS = 30                  # máximo de comentarios a incluir

PIPELINE_STAGES = ["business", "functional", "technical", "developer", "qa"]

_STAGE_LABELS = {
    "business":   "Brief de negocio / Epics RF-XXX",
    "functional": "Análisis funcional + plan de pruebas",
    "technical":  "Análisis técnico (5 secciones)",
    "developer":  "Implementación de código",
    "qa":         "QA / UAT con veredicto",
}

# ---------------------------------------------------------------------------
# Modelo de cache (SQLAlchemy)
# ---------------------------------------------------------------------------

class PipelineInferenceCache(Base):
    __tablename__ = "pipeline_inference_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ado_id: Mapped[int] = mapped_column(Integer, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(60), nullable=False, default=INFERENCE_MODEL)
    cached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_pipeline_cache_ado_id", "ado_id"),)

    def is_fresh(self, ttl_minutes: int = CACHE_TTL_MINUTES) -> bool:
        age = datetime.utcnow() - self.cached_at
        return age < timedelta(minutes=ttl_minutes)

    def to_result(self) -> "PipelineInferenceResult":
        data = json.loads(self.result_json)
        return PipelineInferenceResult(**data)


# ---------------------------------------------------------------------------
# Tipos resultado
# ---------------------------------------------------------------------------

class StageInference:
    def __init__(self, stage: str, done: bool, confidence: float, evidence: str):
        self.stage = stage
        self.done = done
        self.confidence = round(max(0.0, min(1.0, confidence)), 2)
        self.evidence = evidence

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "done": self.done,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


class PipelineInferenceResult:
    def __init__(
        self,
        ado_id: int,
        stages: dict,
        next_suggested: str | None,
        overall_progress: float,
        summary: str,
        inferred_at: str,
        model_used: str,
        source: str = "llm",
    ):
        self.ado_id = ado_id
        self.stages = stages          # dict[str, dict] (serializable)
        self.next_suggested = next_suggested
        self.overall_progress = round(overall_progress, 2)
        self.summary = summary
        self.inferred_at = inferred_at
        self.model_used = model_used
        self.source = source          # "llm" | "cache"

    def to_dict(self) -> dict:
        return {
            "ado_id": self.ado_id,
            "stages": self.stages,
            "next_suggested": self.next_suggested,
            "overall_progress": self.overall_progress,
            "summary": self.summary,
            "inferred_at": self.inferred_at,
            "model_used": self.model_used,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# HTML → texto plano (para limpiar comentarios ADO)
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def get_text(self) -> str:
        return " ".join(self._chunks).strip()


def _strip_html(html: str) -> str:
    if not html:
        return ""
    s = _HTMLStripper()
    try:
        s.feed(html)
        return re.sub(r"\s{2,}", " ", s.get_text())
    except Exception:
        # Fallback: remove tags con regex
        return re.sub(r"<[^>]+>", " ", html).strip()


# ---------------------------------------------------------------------------
# Construcción del contexto ADO
# ---------------------------------------------------------------------------

def _build_ticket_context(ado_id: int) -> str:
    """Fetches full ticket data from ADO and returns a text block for the LLM."""
    from services.ado_client import AdoClient, AdoApiError

    try:
        client = AdoClient()
    except Exception as e:
        raise RuntimeError(f"No se pudo crear AdoClient: {e}") from e

    # Work item principal
    try:
        items = client._batch_get([ado_id])
    except AdoApiError as e:
        raise RuntimeError(f"No se pudo obtener ADO-{ado_id}: {e}") from e

    if not items:
        raise RuntimeError(f"ADO-{ado_id} no encontrado")

    wi = items[0]
    fields = wi.get("fields") or {}
    title = fields.get("System.Title", "Sin título")
    description = _strip_html(fields.get("System.Description") or "")
    wi_type = fields.get("System.WorkItemType", "")
    state = fields.get("System.State", "")
    assigned_to = (fields.get("System.AssignedTo") or {})
    if isinstance(assigned_to, dict):
        assigned_to = assigned_to.get("displayName", "")

    # Comentarios
    comments = client.fetch_comments(ado_id, top=MAX_COMMENTS)

    lines: list[str] = [
        f"TICKET: ADO-{ado_id}",
        f"TIPO: {wi_type}",
        f"TÍTULO: {title}",
        f"ESTADO ADO: {state}",
        f"ASIGNADO A: {assigned_to or 'sin asignar'}",
        "",
        "=== DESCRIPCIÓN ===",
        description[:3000] if description else "(sin descripción)",
        "",
        f"=== COMENTARIOS ({len(comments)}) ===",
    ]

    for i, c in enumerate(comments, 1):
        text = _strip_html(c.get("text", ""))[:MAX_COMMENT_CHARS]
        author = c.get("author", "?")
        date = c.get("date", "")
        lines.append(f"--- Comentario {i} [{author} | {date}] ---")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Llamada al LLM
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Sos un analizador de estado de pipeline de desarrollo de software.
Recibís datos completos de un ticket de Azure DevOps (título, descripción, comentarios)
y determinás qué etapas del pipeline de desarrollo ya fueron completadas.

El pipeline tiene estas etapas, en orden:
1. business   — Brief de negocio convertido en Epics con bloques RF-XXX
2. functional — Análisis funcional + plan de pruebas generado
3. technical  — Análisis técnico con 5 secciones (traducción funcional→técnica, alcance de cambios, plan de pruebas técnico, tests unitarios, notas para el dev)
4. developer  — Implementación de código completada (archivos modificados, commits)
5. qa         — QA/UAT ejecutado con veredicto PASS o FAIL

Para detectar cada etapa, buscá evidencia en los comentarios y descripción:
- business:   menciones de "RF-001", "RF-002", bloques de requerimientos, epics estructurados
- functional: "análisis funcional", "analisis-funcional.md", "plan-de-pruebas", "CUBRE", "GAP", "🔍"
- technical:  "🔬 ANÁLISIS TÉCNICO", "análisis técnico", "alcance de cambios", "tests unitarios", "TU-001"
- developer:  "🚀 IMPLEMENTACIÓN COMPLETADA", "archivos modificados", "commits realizados", implementación
- qa:         "TESTER_COMPLETADO", "veredicto PASS", "veredicto FAIL", "escenarios ejecutados", QA completado

Respondé ÚNICAMENTE con un objeto JSON válido (sin markdown, sin explicaciones extra):
{
  "stages": {
    "business":   {"done": true/false, "confidence": 0.0-1.0, "evidence": "frase corta con la razón"},
    "functional": {"done": true/false, "confidence": 0.0-1.0, "evidence": "frase corta"},
    "technical":  {"done": true/false, "confidence": 0.0-1.0, "evidence": "frase corta"},
    "developer":  {"done": true/false, "confidence": 0.0-1.0, "evidence": "frase corta"},
    "qa":         {"done": true/false, "confidence": 0.0-1.0, "evidence": "frase corta"}
  },
  "next_suggested": "nombre_de_etapa_o_null",
  "overall_progress": 0.0-1.0,
  "summary": "Una oración describiendo el estado actual del ticket"
}
"""


def _call_llm(ticket_context: str, model: str) -> dict:
    """Llama al LLM y devuelve el JSON parseado."""
    import copilot_bridge as bridge

    def _noop_log(level: str, msg: str) -> None:
        logger.debug("[llm] %s: %s", level, msg)

    result = bridge.invoke(
        agent_type="pipeline_inference",
        system=_SYSTEM_PROMPT,
        user=ticket_context,
        on_log=_noop_log,
        execution_id=None,
        model=model,
    )

    raw = result.text.strip()

    # Extraer JSON del output (puede venir con ```json ... ```)
    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if json_match:
        raw = json_match.group(1)

    # Intento 1: parseo directo
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Intento 2: extraer el primer objeto JSON con regex
    obj_match = re.search(r"\{[\s\S]+\}", raw)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"LLM no devolvió JSON válido. Raw: {raw[:400]}")


# ---------------------------------------------------------------------------
# Punto de entrada público
# ---------------------------------------------------------------------------

def infer_pipeline(
    ado_id: int,
    force_refresh: bool = False,
    model: str | None = None,
) -> PipelineInferenceResult:
    """
    Infiere el estado del pipeline para un ticket ADO.

    Usa cache en BD local (TTL=60min). Si force_refresh=True, re-infiere
    siempre. El resultado es reproducible en cualquier máquina con acceso
    al mismo proyecto ADO.

    Args:
        ado_id:        ID del work item en Azure DevOps.
        force_refresh: Si True, ignora cache y re-llama al LLM.
        model:         Modelo LLM a usar (default: gpt-4o-mini).
    """
    effective_model = model or INFERENCE_MODEL

    # 1. Intentar cache
    if not force_refresh:
        with session_scope() as session:
            cached = (
                session.query(PipelineInferenceCache)
                .filter(PipelineInferenceCache.ado_id == ado_id)
                .order_by(PipelineInferenceCache.cached_at.desc())
                .first()
            )
            if cached and cached.is_fresh():
                logger.debug("Pipeline inference cache HIT para ADO-%s", ado_id)
                result = cached.to_result()
                result.source = "cache"
                return result

    # 2. Fetch context from ADO
    logger.info("Pipeline inference: fetching ADO-%s context", ado_id)
    ticket_context = _build_ticket_context(ado_id)

    # 3. Call LLM
    logger.info("Pipeline inference: calling LLM (%s) for ADO-%s", effective_model, ado_id)
    llm_data = _call_llm(ticket_context, effective_model)

    # 4. Parse + validar
    raw_stages = llm_data.get("stages") or {}
    stages: dict[str, dict] = {}
    done_count = 0
    for s in PIPELINE_STAGES:
        sd = raw_stages.get(s) or {}
        done = bool(sd.get("done", False))
        if done:
            done_count += 1
        stages[s] = {
            "stage": s,
            "label": _STAGE_LABELS.get(s, s),
            "done": done,
            "confidence": round(float(sd.get("confidence") or 0.0), 2),
            "evidence": str(sd.get("evidence") or ""),
        }

    overall = done_count / len(PIPELINE_STAGES)
    next_s = llm_data.get("next_suggested")
    if next_s not in PIPELINE_STAGES:
        # Calcular el primero no completado
        next_s = next(
            (s for s in PIPELINE_STAGES if not stages[s]["done"]),
            None,
        )

    now_iso = datetime.utcnow().isoformat()
    result = PipelineInferenceResult(
        ado_id=ado_id,
        stages=stages,
        next_suggested=next_s,
        overall_progress=overall,
        summary=str(llm_data.get("summary") or ""),
        inferred_at=now_iso,
        model_used=effective_model,
        source="llm",
    )

    # 5. Guardar en cache
    result_json = json.dumps(result.to_dict(), ensure_ascii=False)
    with session_scope() as session:
        # Reemplazar cache existente
        old = (
            session.query(PipelineInferenceCache)
            .filter(PipelineInferenceCache.ado_id == ado_id)
            .first()
        )
        if old:
            old.result_json = result_json
            old.model_used = effective_model
            old.cached_at = datetime.utcnow()
        else:
            session.add(PipelineInferenceCache(
                ado_id=ado_id,
                result_json=result_json,
                model_used=effective_model,
                cached_at=datetime.utcnow(),
            ))

    return result


def invalidate_cache(ado_id: int) -> None:
    """Elimina la entrada de cache para forzar re-inferencia en la próxima llamada."""
    with session_scope() as session:
        session.query(PipelineInferenceCache).filter(
            PipelineInferenceCache.ado_id == ado_id
        ).delete()
