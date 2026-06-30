"""Plan 53 — Selector adaptativo de modelo/effort por confidence de grounding.

Función PURA: confidence (0.0–1.0 o None) → propuesta (model, effort).
NO hace I/O. NO decide el clamp final (eso es llm_router). PROPONE; el caller pasa
la propuesta por clamp_model + _clamp_effort_for_model como red de seguridad.

Separación de responsabilidades:
- `select()` — función pura, testeable sin mocks, sin runtime.
- `_load_last_project_confidence()` — capa de I/O (DB), privada, separada de la
  lógica pura. El caller (api/agents.py) la invoca solo con flag ON.

Tabla de fallback por runtime (documentada, no en código — la capa de clamp ya cubre):
- claude_code_cli: soporta Sonnet 4.6 + Opus 4.8 (allowlist); efforts low/medium/high/max.
- codex_cli: model_override Claude es inerte (runner usa su modelo nativo); effort viaja
  pero el runner lo interpreta según su matriz. Degradación = default del runtime.
- github_copilot: usa copilot bridge; model_override Claude inerte. Igual que codex.
El select() NO conoce el runtime (G2: función pura idéntica para los 3). La degradación
la maneja el clamp existente en api/agents.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from services import llm_router

logger = logging.getLogger("stacky_agents.adaptive_selector")

# Modelos canónicos (reusar nombres de llm_router; NO hardcodear strings sueltos).
_MODEL_SONNET = llm_router.CLAUDE_CAP_MODEL          # "claude-sonnet-4-6"
_MODEL_OPUS = "claude-opus-4-8"                      # debe estar en llm_router._OPUS_ALLOWLIST

# Guard de coherencia (cero costo, atrapa drift de allowlist en import):
assert _MODEL_OPUS in llm_router._OPUS_ALLOWLIST, (
    "adaptive_selector: _MODEL_OPUS debe estar en llm_router._OPUS_ALLOWLIST"
)

# TABLA DE BANDAS — orden de mayor a menor confianza.
# Cada banda: (umbral_inclusivo_inferior, model_propuesto, effort_propuesto, etiqueta).
# confidence se compara como >= umbral => el umbral pertenece a la banda SUPERIOR.
# Diseño: confianza alta -> barato (Sonnet/low-medium); confianza baja -> caro (Opus/max).
#
# v1: bandas como constantes código (hardcodeadas por diseño deliberado).
# Evolución a config: plan futuro si hay análisis de impacto en K1/K2.
ADAPTIVE_BANDS: tuple[tuple[float, str, str, str], ...] = (
    (0.85, _MODEL_SONNET, "low",    "very_high_confidence"),
    (0.70, _MODEL_SONNET, "medium", "high_confidence"),
    (0.50, _MODEL_SONNET, "high",   "medium_confidence"),
    (0.30, _MODEL_OPUS,   "high",   "low_confidence"),
    (0.00, _MODEL_OPUS,   "max",    "very_low_confidence"),
)


@dataclass(frozen=True)
class Selection:
    model: str | None     # id de modelo Claude propuesto (None = usar default del runner)
    effort: str           # uno de {"low","medium","high","xhigh","max"}
    reason: str           # traza humana de por qué (banda de confidence aplicada)


def select(
    confidence: float | None,
    *,
    base_model: str | None,
    base_effort: str,
) -> Selection:
    """Función PURA: confidence (0.0–1.0 o None) → propuesta (model, effort).

    NOTA IMPORTANTE: esta función NO aplica el clamp final. Devuelve una propuesta
    cruda. El caller (api/agents.py) la pasa siempre por clamp_model(allow_opus=True)
    y _clamp_effort_for_model como red de seguridad (G3).

    Casos borde explícitos:
    - confidence None o no-numérico → NO hay señal → devuelve base intacto.
    - confidence fuera de [0,1] → clamp a [0,1] antes de buscar banda.
    - bordes exactos de umbral: >= umbral → banda SUPERIOR (ej: 0.70 → high_confidence).
    """
    # CASO BORDE 1 — confidence ausente (None) o no-numérico:
    #   NO hay señal anticipada -> NO tocar nada. Propuesta = los defaults entrantes.
    if confidence is None or not isinstance(confidence, (int, float)):
        return Selection(model=base_model, effort=base_effort,
                         reason="no_confidence_signal")

    c = float(confidence)
    # CASO BORDE 2 — fuera de rango: clamp a [0.0, 1.0].
    if c < 0.0:
        c = 0.0
    elif c > 1.0:
        c = 1.0

    # CASO BORDE 3 — bordes exactos: comparación >= → el umbral pertenece a la banda SUPERIOR.
    for threshold, model, effort, label in ADAPTIVE_BANDS:
        if c >= threshold:
            return Selection(model=model, effort=effort, reason=f"adaptive:{label}({c:.2f})")

    # Inalcanzable (la última banda tiene umbral 0.0 y c>=0.0 siempre). Defensa:
    return Selection(model=base_model, effort=base_effort, reason="fallback_unreached")


def _load_last_project_confidence(project_name: str | None) -> float | None:
    """Confidence de grounding del run más reciente del proyecto (señal anticipada).

    Consulta la DB para obtener el último epic_summary persistido del proyecto
    y extrae su confidence (la misma señal que agrega grounding_observatory).
    None si no hay historial.

    ASIMETRÍA TEMPORAL — DISEÑO CENTRAL (C1):
    El confidence del run ACTUAL nace DESPUÉS del run. El selector decide ANTES.
    Por eso se usa el confidence del run PREVIO del mismo proyecto como señal
    anticipada. Este es el patrón validado por el observatorio (plan 42/44).

    CONTAMINACIÓN (C1): en proyectos con briefs heterogéneos, el confidence del
    run previo puede no representar al brief actual. Mitigaciones:
    1. El threshold defensivo 0.3 evita amplificar ruido extremo.
    2. El override manual del operador siempre gana (G4).
    3. El test test_heterogeneous_briefs_use_last_confidence documenta la asunción.

    I/O aislada acá; la decisión vive en select() (pura).
    """
    if not project_name:
        return None
    try:
        from db import session_scope
        from models import AgentExecution, Ticket

        with session_scope() as session:
            # Buscar el último run del proyecto con epic_summary que tenga confidence.
            q = (
                session.query(AgentExecution)
                .filter(AgentExecution.metadata_json.isnot(None))
                .filter(AgentExecution.metadata_json.like('%epic_summary%'))
                .order_by(AgentExecution.started_at.desc())
            )
            for ex in q:
                try:
                    md = ex.metadata_dict
                except Exception:  # noqa: BLE001 — metadata corrupta → omitir
                    continue
                summary = md.get("epic_summary")
                if not isinstance(summary, dict):
                    continue
                # Filtro best-effort por proyecto (mismo patrón que _collect_epic_summaries).
                ticket = session.get(Ticket, ex.ticket_id) if ex.ticket_id else None
                proj_name = getattr(ticket, "stacky_project_name", None) if ticket else None
                if proj_name and proj_name != project_name:
                    continue
                # Extraer confidence del summary.
                conf_val = summary.get("confidence")
                if isinstance(conf_val, (int, float)):
                    return float(conf_val)
        return None
    except (KeyError, TypeError, AttributeError) as e:
        # Errores esperados: estructura malformada.
        logger.warning(
            "_load_last_project_confidence: estructura invalida: %s", e,
        )
        return None
    except Exception as e:  # noqa: BLE001 — errores inesperados: DB, permisos, etc.
        logger.error(
            "_load_last_project_confidence: error inesperado: %s", e,
        )
        return None
