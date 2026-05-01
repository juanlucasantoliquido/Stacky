"""
pipeline_reconciler — Fuente de verdad canónica del estado del pipeline.

Problema histórico:
    El estado vive en dos lugares — state.json["estado"] y los archivos del
    folder del ticket (flags, .md). Cuando divergen (crash del agente, unstuck
    que toca archivos sin actualizar JSON, carrera del watcher), el pipeline
    queda atascado silenciosamente y nadie avanza al ticket.

Solución:
    1. `derive_stage_from_folder(folder)` — única función que mira los archivos
       y devuelve (estado_real, next_stage_sugerida, evidencia).
    2. `reconcile_ticket_entry(folder, entry)` — compara derivado vs state.json
       y devuelve un plan de acción (sync_state, launch_stage, mark_stale).
    3. Thread reconciliador que corre cada N segundos y aplica el plan.

Cualquier código que necesite "¿en qué estado real está este ticket?" debe
llamar a `derive_stage_from_folder` — nunca inspeccionar archivos ad-hoc.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


# ── Archivos canónicos por etapa ───────────────────────────────────────────────
# El orden importa para el diagnóstico: primero errores, luego en-curso, luego
# completados.

# Flag de bloqueo humano — gana a todo lo demás
BLOQUEO_HUMANO_FLAG = "BLOQUEO_HUMANO.flag"

# Flags de "agente corriendo ahora mismo"
EN_CURSO_FLAGS = {
    "pm":     "PM_AGENTE_EN_CURSO.flag",
    "dev":    "DEV_AGENTE_EN_CURSO.flag",
    "tester": "TESTER_AGENTE_EN_CURSO.flag",
    "doc":    "DOC_AGENTE_EN_CURSO.flag",
}

# Flags de error explícito
ERROR_FLAGS = {
    "pm":     "PM_ERROR.flag",
    "dev":    "DEV_ERROR.flag",
    "tester": "TESTER_ERROR.flag",
    "doc":    "DOC_ERROR.flag",
}

# Sentinelas de completado exitoso
COMPLETADO_FILES = {
    "pm":     "PM_COMPLETADO.flag",
    "dev":    "DEV_COMPLETADO.md",
    "tester": "TESTER_COMPLETADO.md",
    "doc":    "DOC_COMPLETADO.flag",
}


# ── Resultado de la derivación ─────────────────────────────────────────────────

@dataclass
class DerivedState:
    """
    Lo que el filesystem dice que es la verdad, independientemente de state.json.

    Campos:
        estado: el estado "real" que debería estar en state.json según los
                archivos. Uno de: bloqueo_humano, pm_en_proceso, dev_en_proceso,
                tester_en_proceso, error_pm, qa_rework, error_tester, error_doc,
                pm_completado, dev_completado, tester_completado, pm_revision,
                completado, pendiente_pm.
        next_stage: cuál etapa correspondería lanzar (None si no hay nada que
                    lanzar — completado, bloqueo, o ya corriendo).
        evidence: lista de archivos detectados que justifican la conclusión.
        qa_verdict: si tester completó, el veredicto parseado (APROBADO /
                    CON OBSERVACIONES / RECHAZADO / None).
    """
    estado:      str
    next_stage:  Optional[str]
    evidence:    list[str]           = field(default_factory=list)
    qa_verdict:  Optional[str]       = None


def _has(folder: str, name: str) -> bool:
    return os.path.exists(os.path.join(folder, name))


def _parse_qa_verdict_safe(folder: str) -> Optional[str]:
    """
    Lee TESTER_COMPLETADO.md y extrae veredicto con prioridad RECHAZADO >
    CON OBSERVACIONES > APROBADO. Devuelve None si no existe / no parseable.
    No depende de otros módulos (evita import circular).
    """
    path = os.path.join(folder, "TESTER_COMPLETADO.md")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read().upper()
    except Exception:
        return None
    for v in ("RECHAZADO", "CON OBSERVACIONES", "APROBADO"):
        if v in content:
            return v
    return None


def derive_stage_from_folder(folder: str) -> DerivedState:
    """
    Determina el estado real del pipeline inspeccionando archivos del folder.

    Reglas (en orden de prioridad):
      1. BLOQUEO_HUMANO.flag → estado="bloqueo_humano", next=None
      2. Cualquier *_AGENTE_EN_CURSO.flag → estado={stage}_en_proceso, next=None
      3. DEV_ERROR.flag → estado="qa_rework" (dev debe rehacer), next="dev"
      4. TESTER_ERROR.flag → estado="error_tester", next="tester"
      5. PM_ERROR.flag → estado="error_pm", next="pm"
      6. DOC_ERROR.flag → estado="error_doc", next="doc"
      7. TESTER_COMPLETADO.md existe → parsear veredicto:
         - RECHAZADO → estado="pm_revision", next="pm"
         - APROBADO / CON OBSERVACIONES → estado="completado", next=None
      8. DEV_COMPLETADO.md (sin TESTER_COMPLETADO.md) → estado="dev_completado", next="tester"
      9. PM_COMPLETADO.flag (sin DEV_COMPLETADO.md) → estado="pm_completado", next="dev"
     10. Nada (carpeta vacía, sin evidencia) → estado="pendiente_pm", next=None
         (el reconciliador no debe auto-lanzar PM a partir de la nada; esto
         requiere trigger explícito del usuario, del Rally, o de /api/run_pipeline.
         Sincronizamos el estado para coherencia pero no disparamos la etapa.)
    """
    if not folder or not os.path.isdir(folder):
        return DerivedState("desconocido", None, ["folder_no_existe"])

    evidence: list[str] = []

    # 1. Bloqueo humano gana a todo
    if _has(folder, BLOQUEO_HUMANO_FLAG):
        evidence.append(BLOQUEO_HUMANO_FLAG)
        return DerivedState("bloqueo_humano", None, evidence)

    # 2. Agente corriendo ahora — el estado real es `*_en_proceso`
    for stage, flag in EN_CURSO_FLAGS.items():
        if _has(folder, flag):
            evidence.append(flag)
            return DerivedState(f"{stage}_en_proceso", None, evidence)

    # 3-6. Flags de error (orden: DEV, TESTER, PM, DOC)
    if _has(folder, ERROR_FLAGS["dev"]):
        evidence.append(ERROR_FLAGS["dev"])
        # DEV_ERROR = QA rechazó y pidió rework → estado canónico "qa_rework"
        return DerivedState("qa_rework", "dev", evidence)

    if _has(folder, ERROR_FLAGS["tester"]):
        evidence.append(ERROR_FLAGS["tester"])
        return DerivedState("error_tester", "tester", evidence)

    if _has(folder, ERROR_FLAGS["pm"]):
        evidence.append(ERROR_FLAGS["pm"])
        return DerivedState("error_pm", "pm", evidence)

    if _has(folder, ERROR_FLAGS["doc"]):
        evidence.append(ERROR_FLAGS["doc"])
        return DerivedState("error_doc", "doc", evidence)

    # 7. Tester completó → bifurcar por veredicto
    if _has(folder, COMPLETADO_FILES["tester"]):
        evidence.append(COMPLETADO_FILES["tester"])
        verdict = _parse_qa_verdict_safe(folder)
        if verdict == "RECHAZADO":
            return DerivedState("pm_revision", "pm", evidence, qa_verdict=verdict)
        # APROBADO, CON OBSERVACIONES o DESCONOCIDO → tratamos como completado
        return DerivedState("completado", None, evidence, qa_verdict=verdict)

    # 8. Dev completó pero tester no
    if _has(folder, COMPLETADO_FILES["dev"]):
        evidence.append(COMPLETADO_FILES["dev"])
        return DerivedState("dev_completado", "tester", evidence)

    # 9. PM completó pero dev no
    if _has(folder, COMPLETADO_FILES["pm"]):
        evidence.append(COMPLETADO_FILES["pm"])
        return DerivedState("pm_completado", "dev", evidence)

    # 10. Nada → pendiente PM (sin auto-launch; requiere trigger explícito)
    # Evita el storm de arranque: tickets nuevos con carpeta vacía no deben
    # disparar PM en paralelo desde el reconciliador.
    return DerivedState("pendiente_pm", None, evidence)


# ── Plan de reconciliación ─────────────────────────────────────────────────────

@dataclass
class ReconcileResult:
    """
    Plan de acción tras comparar derivación con state.json.

    Campos:
        ticket_id: str
        coherent: True si state.json["estado"] coincide con derivado.
        needs_sync: True si hay que actualizar state.json.
        synthetic_state: el nuevo estado a setear en state.json (None si no cambia).
        launch_stage: etapa a invocar (None si no lanzar nada).
        is_stale: ticket en estado _en_proceso sin AGENTE_EN_CURSO o con exceso de edad.
        stale_reason: explicación humana del stale.
        derived: el DerivedState completo (para debug/UI).
        stored_estado: lo que está actualmente en state.json.
        warnings: lista de avisos no-bloqueantes.
    """
    ticket_id:       str
    coherent:        bool
    needs_sync:      bool                = False
    synthetic_state: Optional[str]       = None
    launch_stage:    Optional[str]       = None
    is_stale:        bool                = False
    stale_reason:    Optional[str]       = None
    derived:         Optional[DerivedState] = None
    stored_estado:   Optional[str]       = None
    warnings:        list[str]           = field(default_factory=list)


# Estados en los que reconciliar con el filesystem (los demás son estables)
_RECONCILABLE_STORED = frozenset((
    "pendiente_pm",
    "pm_en_proceso", "pm_completado", "error_pm", "pm_revision",
    "pm_revision_completado",
    "dev_en_proceso", "dev_completado", "error_dev", "qa_rework",
    "tester_en_proceso", "tester_completado", "error_tester",
    "doc_en_proceso", "error_doc",
    "completado",
    "bloqueo_humano",
))


def _last_invoke_at(entry: dict) -> Optional[datetime]:
    li = (entry.get("last_invoke") or {}).get("at")
    if not li:
        return None
    try:
        return datetime.fromisoformat(li)
    except Exception:
        return None


def _last_en_proceso_at(entry: dict, stage: str) -> Optional[datetime]:
    ts = entry.get(f"{stage}_en_proceso_at") or entry.get(f"{stage}_inicio_at")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def reconcile_ticket_entry(
    ticket_id:        str,
    folder:           Optional[str],
    entry:            dict,
    *,
    stale_after_min:  int  = 20,
    debounce_seconds: int  = 45,
    now:              Optional[datetime] = None,
) -> ReconcileResult:
    """
    Compara el estado derivado del folder con lo que dice state.json.

    Args:
        ticket_id: id del ticket (para logging).
        folder: carpeta del ticket (None/inexistente → coherent=True, no-op).
        entry: diccionario state.json["tickets"][ticket_id].
        stale_after_min: un ticket *_en_proceso sin progreso durante más de
                         este tiempo se considera stale.
        debounce_seconds: si hubo una invocación hace menos de esto, no
                          relanzamos (evita duplicación tras un set_state).
        now: inyectable para tests.

    Returns:
        ReconcileResult con plan de acción.
    """
    now = now or datetime.now()
    stored = (entry or {}).get("estado", "") or ""
    res = ReconcileResult(
        ticket_id=ticket_id,
        coherent=True,
        stored_estado=stored,
    )

    if not folder or not os.path.isdir(folder):
        res.warnings.append("folder_no_existe")
        return res

    derived = derive_stage_from_folder(folder)
    res.derived = derived

    # ── Detección de stale ────────────────────────────────────────────────
    # Ticket *_en_proceso sin que haya un AGENTE_EN_CURSO.flag en el folder
    # ni actividad reciente → el agente probablemente murió.
    if stored.endswith("_en_proceso"):
        stage = stored.split("_en_proceso")[0]
        en_curso_flag = EN_CURSO_FLAGS.get(stage)
        has_en_curso = en_curso_flag and _has(folder, en_curso_flag)

        started_at = _last_en_proceso_at(entry, stage)
        invoked_at = _last_invoke_at(entry)
        age_ref    = started_at or invoked_at
        age_min    = None
        if age_ref:
            age_min = (now - age_ref).total_seconds() / 60.0

        if not has_en_curso and derived.estado != stored and age_min and age_min > 2:
            # No hay EN_CURSO, filesystem ya no dice "en proceso", y ya pasaron
            # más de 2 min — el agente murió sin terminar.
            res.is_stale = True
            res.stale_reason = (
                f"En {stored} hace {age_min:.1f} min sin {en_curso_flag} — "
                f"filesystem dice {derived.estado}"
            )
        elif has_en_curso and age_min and age_min > stale_after_min:
            # EN_CURSO existe pero muy viejo — agente colgado
            res.is_stale = True
            res.stale_reason = (
                f"{en_curso_flag} hace {age_min:.1f} min — agente probablemente colgado"
            )
        elif not has_en_curso and age_min and age_min > stale_after_min:
            res.is_stale = True
            res.stale_reason = (
                f"En {stored} hace {age_min:.1f} min sin EN_CURSO — probable crash"
            )

    # ── Comparación derivado vs almacenado ────────────────────────────────
    if stored == derived.estado:
        # Ya coherente — nada que hacer
        return res

    # Casos donde aceptamos divergencia sin forzar sync:
    #   - stored es un estado "superior" del pipeline (ej: stored=pm_revision
    #     porque el watcher bifurcó tras RECHAZADO, y folder sigue con
    #     TESTER_COMPLETADO.md). Esos son válidos y no debemos pisarlos.
    _OVERRIDE_OK = {
        # stored: set de estados derivados aceptables (no fuerza sync)
        "pm_revision":              {"completado"},    # bifurcación post-tester
        "pm_revision_completado":   {"pm_revision", "completado"},
        "dev_rework_completado":    {"dev_completado"},
        "stagnation_detected":      {"completado", "pm_revision", "qa_rework"},
    }
    if derived.estado in _OVERRIDE_OK.get(stored, set()):
        return res

    # Si el derivado es "en_proceso" pero el stored es un estado terminal,
    # NO pisamos — el en_proceso es transitorio y se auto-limpia cuando el
    # agente termina. El watcher normal lo va a corregir.
    if derived.estado.endswith("_en_proceso") and not stored.endswith("_en_proceso"):
        res.warnings.append(f"derivado {derived.estado} ignorado (stored={stored} estable)")
        return res

    # ── Divergencia real — hay que sincronizar ────────────────────────────
    res.coherent = False
    res.needs_sync = True
    res.synthetic_state = derived.estado

    # ── Decisión de lanzar etapa ──────────────────────────────────────────
    # No lanzar si:
    #   - Bloqueo humano
    #   - Ya hay un agente corriendo (derivado *_en_proceso)
    #   - Hubo un last_invoke muy reciente (debounce)
    #   - El ticket está en un estado terminal sin next_stage
    if derived.estado == "bloqueo_humano":
        return res
    if derived.estado.endswith("_en_proceso"):
        return res
    if not derived.next_stage:
        return res

    invoked_at = _last_invoke_at(entry)
    if invoked_at:
        elapsed = (now - invoked_at).total_seconds()
        if elapsed < debounce_seconds:
            res.warnings.append(
                f"debounce: last_invoke hace {elapsed:.1f}s < {debounce_seconds}s"
            )
            return res

    res.launch_stage = derived.next_stage
    return res


# ── Mapa de compatibilidad con _invoke_stage ──────────────────────────────────
# Los estados "canónicos" del derivador se mapean 1:1 a los estados que usa
# dashboard_server._invoke_stage y el kick_map del Rally.

def coherent_with(stored_estado: str, derived_estado: str) -> bool:
    """True si derived y stored representan el mismo punto del pipeline."""
    if stored_estado == derived_estado:
        return True
    # pm_revision es un estado terminal post-tester (bifurcación). El derivador
    # sin TESTER_COMPLETADO.md devolvería otro estado; con él devuelve
    # "pm_revision" o "completado" según veredicto. Aceptamos ambos.
    equivalences = [
        {"pm_revision", "pm_revision_completado"},
        {"dev_completado", "dev_rework_completado"},
    ]
    for eq in equivalences:
        if stored_estado in eq and derived_estado in eq:
            return True
    return False
