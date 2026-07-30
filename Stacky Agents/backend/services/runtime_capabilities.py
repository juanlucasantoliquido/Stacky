"""Plan 264 — la ÚNICA matriz de capacidades de runtime/modelo/effort.

Una sola fuente para "qué modelos y qué niveles de esfuerzo admite cada
herramienta, cómo degrada cada combinación y qué efecto tiene HOY con la
configuración vigente". Reemplaza las ~12 copias de la lista de efforts
esparcidas por `api/` y `services/`, y NORMALIZA el catálogo vivo
(`config/model_catalog.json`), que hoy trae `codex_cli` incompleto:
`efforts: []`, `default_effort: null`, `models: [""]`.

Regla de imports (§3.8 / R1 del plan): este módulo importa `model_catalog`,
`llm_router` y `config` SIEMPRE dentro de las funciones, nunca a nivel de
módulo — `model_catalog` importa `claude_code_cli_runner` (dentro de
`_merge_probe`), que en una fase futura podría importar este módulo; resolver
esos símbolos en el top-level abriría un ciclo.

Binding de `config`: este archivo usa `from config import config as _cfg`
dentro de cada función ⇒ `_cfg` YA es la instancia (`config.py:2137`). Se lee
SIEMPRE con `getattr(_cfg, "STACKY_X", default)`. Nunca `_cfg.config`.
"""
from __future__ import annotations

import re

# El ÚNICO literal de efforts del backend. Todo lo demás delega acá.
# Esto es el VOCABULARIO DE VALIDACIÓN (qué strings son legales). La FUENTE DE
# PRESENTACIÓN (labels, orden, soporte por modelo) sigue siendo el catálogo:
# config/model_catalog.json — normalizado por capabilities_for() más abajo.
EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
EFFORT_ORDER: dict[str, int] = {e: i for i, e in enumerate(EFFORTS)}

RUNTIMES: tuple[str, ...] = ("claude_code_cli", "codex_cli", "github_copilot")

# Cómo materializa el effort cada runtime. Declarativo, no inferido.
EFFORT_MODE: dict[str, str] = {
    "claude_code_cli": "nativo",              # el CLI acepta el esfuerzo directo
    "codex_cli":       "presupuesto_turnos",  # codex_cli_runner.py:580 — no hay --effort
    "github_copilot":  "no_aplica",           # el bridge no expone esfuerzo
}

# Fracción del CAP de turnos por esfuerzo en codex. SIEMPRE <= 1.0: el effort
# sólo mueve el presupuesto HACIA ABAJO desde el techo. `medium` vale 1.0 A
# PROPÓSITO: es EXACTAMENTE lo que hace el código de hoy
# (codex_cli_runner.py:591-592 sólo divide cuando el esfuerzo es `low`).
CODEX_EFFORT_TURN_FACTOR: dict[str, float] = {
    "low": 0.5, "medium": 1.0, "high": 1.0, "xhigh": 1.0, "max": 1.0,
}


def is_valid_effort(effort: str | None) -> bool:
    """True si `effort` (case-insensitive, sin espacios) está en EFFORTS."""
    if not effort:
        return False
    return effort.strip().lower() in EFFORTS


def _normalized_block(runtime: str) -> tuple[dict, str]:
    """Bloque crudo del catálogo para `runtime` (dict vacío si no existe o si
    el catálogo no pudo leerse) + el effort_mode declarado (default no_aplica
    para runtimes desconocidos)."""
    effort_mode = EFFORT_MODE.get(runtime, "no_aplica")
    try:
        from services.model_catalog import load_model_catalog
        catalog = load_model_catalog()
    except Exception:  # noqa: BLE001 — el catálogo nunca puede tumbar esto
        catalog = {"runtimes": {}}
    bloque = (catalog.get("runtimes") or {}).get(runtime) or {}
    return bloque, effort_mode


def capabilities_for(runtime: str) -> dict:
    """Capacidades REALES de un runtime, leyendo y NORMALIZANDO el catálogo vivo.

    Nunca lanza, nunca devuelve None. Devuelve siempre las claves del
    contrato (ver docstring del plan 264 F1): runtime, known, effort_mode,
    effort_effective_now, supports_model, supports_effort, models, efforts,
    default_model, default_effort, effort_note.
    """
    known = runtime in RUNTIMES
    bloque, effort_mode = _normalized_block(runtime)

    # Regla 1 — ningún modelo con id vacío (el catálogo trae [""] para codex).
    models = [m for m in (bloque.get("models") or []) if (m.get("id") or "").strip()]

    # Reglas 2/3 — efforts normalizados.
    if effort_mode == "no_aplica":
        efforts: list[dict] = []
    else:
        efforts = bloque.get("efforts") or [{"id": e, "label": e} for e in EFFORTS]

    # Regla 4 — default_effort normalizado.
    raw_default_effort = bloque.get("default_effort")
    if raw_default_effort in EFFORTS:
        default_effort = raw_default_effort
    elif effort_mode != "no_aplica":
        default_effort = "medium"
    else:
        default_effort = None

    # Regla 5 — default_model normalizado (nunca "").
    raw_default_model = (bloque.get("default_model") or "").strip()
    if raw_default_model:
        default_model = raw_default_model
    elif models:
        default_model = models[0].get("id")
    else:
        default_model = None

    from config import config as _cfg
    if effort_mode == "nativo":
        effort_effective_now = True
    elif effort_mode == "presupuesto_turnos":
        effort_effective_now = getattr(_cfg, "STACKY_RUNAWAY_MAX_TURNS", 0) > 0
    else:
        effort_effective_now = False

    if effort_mode == "nativo":
        effort_note = "El esfuerzo se le pasa directo a la herramienta."
    elif effort_mode == "presupuesto_turnos":
        if effort_effective_now:
            effort_note = (
                "Codex no acepta un esfuerzo explícito: se traduce a cuántos "
                "turnos de trabajo se le permiten, siempre por debajo del "
                "límite configurado."
            )
        else:
            effort_note = (
                "Codex no acepta un esfuerzo explícito: se traduce a turnos "
                "de trabajo. Hoy no hay límite de turnos configurado, así "
                "que tu elección queda registrada pero no cambia esta corrida."
            )
    else:
        effort_note = "Esta herramienta no expone niveles de esfuerzo; el selector no se muestra."

    return {
        "runtime": runtime,
        "known": known,
        "effort_mode": effort_mode,
        "effort_effective_now": effort_effective_now,
        "supports_model": len(models) > 0,
        "supports_effort": effort_mode != "no_aplica",
        "models": models,
        "efforts": efforts,
        "default_model": default_model,
        "default_effort": default_effort,
        "effort_note": effort_note,
    }


def clamp_selection(
    runtime: str, model: str | None, effort: str | None, *, allow_opus: bool = False
) -> dict:
    """Ajusta (model, effort) a lo que el runtime realmente soporta. Nunca lanza.

    Devuelve {"model", "effort", "effort_requested", "degraded", "reason"}.
    """
    effort_requested = effort

    from config import config as _cfg
    if not getattr(_cfg, "STACKY_RUNTIME_CAPABILITIES_ENABLED", True):
        return {
            "model": model, "effort": effort, "effort_requested": effort_requested,
            "degraded": False, "reason": None,
        }

    caps = capabilities_for(runtime)
    degraded = False
    reason: str | None = None
    final_model = model

    if runtime == "claude_code_cli":
        from services.llm_router import clamp_model
        new_model = clamp_model(model, allow_opus=allow_opus)
        if model and new_model != model:
            degraded = True
            reason = f"modelo degradado a {new_model} (tier no permitido sin allow_opus)"
        final_model = new_model

    if caps["effort_mode"] == "no_aplica":
        final_effort = None
        degraded = True
        reason = reason or f"{runtime} no expone niveles de esfuerzo"
    elif not is_valid_effort(effort):
        final_effort = caps["default_effort"]
        degraded = True
        reason = reason or f"esfuerzo inválido, se usó el default '{final_effort}'"
    elif runtime == "claude_code_cli":
        from services.llm_router import clamp_effort_for_model
        normalized = effort.strip().lower()  # type: ignore[union-attr]
        clamped = clamp_effort_for_model(normalized, final_model)
        if clamped != normalized:
            degraded = True
            reason = reason or f"esfuerzo degradado a '{clamped}' para el modelo {final_model}"
        final_effort = clamped
    else:
        final_effort = effort.strip().lower()  # type: ignore[union-attr]

    return {
        "model": final_model,
        "effort": final_effort,
        "effort_requested": effort_requested,
        "degraded": degraded,
        "reason": reason,
    }


def codex_turn_budget(effort: str | None, cap_turns: int) -> int:
    """Turnos que le corresponden a Codex para ese esfuerzo.

    CONTRATO DURO: `cap_turns <= 0` significa SIN LÍMITE
    (`RunLimits(max_turns=0)` = sin límite, `harness/runaway_guard.py`) ⇒
    devuelve SIEMPRE 0. Con `cap_turns > 0`: `max(1, int(cap_turns * factor))`,
    nunca mayor que `cap_turns`. Effort inválido o None ⇒ `cap_turns` sin
    cambio. Nunca lanza.
    """
    if cap_turns is None or cap_turns <= 0:
        return 0
    normalized = (effort or "").strip().lower()
    factor = CODEX_EFFORT_TURN_FACTOR.get(normalized)
    if factor is None:
        return cap_turns
    return max(1, int(cap_turns * factor))


# ---------------------------------------------------------------------------
# F3 — resolve_run_selection(): una sola cascada de precedencia
# ---------------------------------------------------------------------------

def resolve_run_selection(
    *,
    runtime: str,
    model: str | None = None,
    effort: str | None = None,
    project_name: str | None = None,
    adaptive_effort: str | None = None,
    allow_opus: bool = False,
) -> dict:
    """Resuelve la selección final con esta precedencia EXACTA (mayor a menor):

      1. `model` / `effort` explícitos de la request        -> origen "explicito"
      2. preferencia guardada del proyecto (si la flag ON)  -> origen "preferencia"
      3. `adaptive_effort` (sólo para effort; es PISO, no techo) -> origen "adaptativo"
      4. default_model / default_effort NORMALIZADOS del catálogo -> "default_catalogo"

    Después aplica clamp_selection() sobre el resultado. Nunca lanza: ante
    cualquier problema cae al paso 4.
    """
    try:
        caps = capabilities_for(runtime)
        pref = load_run_preference(project_name) or {}

        origen_model = "default_catalogo"
        final_model = caps.get("default_model")
        if model:
            origen_model = "explicito"
            final_model = model
        elif pref.get("model"):
            origen_model = "preferencia"
            final_model = pref.get("model")

        origen_effort = "default_catalogo"
        final_effort = caps.get("default_effort")
        if effort:
            origen_effort = "explicito"
            final_effort = effort
        elif pref.get("effort"):
            origen_effort = "preferencia"
            final_effort = pref.get("effort")
        elif adaptive_effort:
            # Piso, no techo: sólo aplica si el operador no eligió ni tiene
            # preferencia guardada.
            origen_effort = "adaptativo"
            final_effort = adaptive_effort

        clamped = clamp_selection(runtime, final_model, final_effort, allow_opus=allow_opus)
        return {
            "runtime": runtime,
            "model": clamped["model"],
            "effort": clamped["effort"],
            "effort_requested": clamped["effort_requested"],
            "degraded": clamped["degraded"],
            "reason": clamped["reason"],
            "origen_model": origen_model,
            "origen_effort": origen_effort,
        }
    except Exception:  # noqa: BLE001 — nunca lanza, cae al default del catálogo
        return {
            "runtime": runtime,
            "model": None,
            "effort": None,
            "effort_requested": effort,
            "degraded": False,
            "reason": None,
            "origen_model": "default_catalogo",
            "origen_effort": "default_catalogo",
        }


# ---------------------------------------------------------------------------
# F4(a) — persistencia de la preferencia por proyecto
# ---------------------------------------------------------------------------

_PREF_KEY_PREFIX = "runSelection."
_PREF_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def pref_key_for(project_name: str | None) -> str:
    """Clave válida para `_UI_KEY_RE` a partir de CUALQUIER nombre de proyecto:
    espacios, acentos y paréntesis se reemplazan por '-'. Determinista y
    estable. `None` -> 'runSelection.__default__'. Resultado <= 128 chars."""
    if not project_name or not project_name.strip():
        return f"{_PREF_KEY_PREFIX}__default__"
    safe = _PREF_SAFE.sub("-", project_name.strip())
    return f"{_PREF_KEY_PREFIX}{safe}"[:128]


def load_run_preference(project_name: str | None) -> dict | None:
    """Lee la preferencia guardada del proyecto vía `api.preferences.read_ui_pref`.

    `None` si no hay, si `STACKY_RUN_SELECTION_PREFS_ENABLED` está OFF, si el
    store de preferencias de UI está deshabilitado, o ante CUALQUIER error.
    Nunca lanza."""
    try:
        from config import config as _cfg
        if not getattr(_cfg, "STACKY_RUN_SELECTION_PREFS_ENABLED", True):
            return None
        from api.preferences import read_ui_pref
        value = read_ui_pref(pref_key_for(project_name))
        return value if isinstance(value, dict) else None
    except Exception:  # noqa: BLE001
        return None


def save_run_preference(project_name: str | None, sel: dict) -> bool:
    """Guarda `{"runtime","model","effort"}` validado con `clamp_selection()`.

    Devuelve `False` (sin lanzar) si la flag está OFF o el guardado falla."""
    try:
        from config import config as _cfg
        if not getattr(_cfg, "STACKY_RUN_SELECTION_PREFS_ENABLED", True):
            return False
        runtime = sel.get("runtime")
        clamped = clamp_selection(runtime, sel.get("model"), sel.get("effort"))
        payload = {
            "runtime": runtime,
            "model": clamped["model"],
            "effort": clamped["effort"],
        }
        from api.preferences import write_ui_pref
        return bool(write_ui_pref(pref_key_for(project_name), payload))
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# F4(b) — historial: build_model_effort_trace / _persist_model_effort_trace
# (mudadas de claude_code_cli_runner.py, Plan 212 F7; el símbolo original
# queda ahí como delegador — hay callers por nombre, incluidos tests del 212)
# ---------------------------------------------------------------------------

def build_model_effort_trace(
    *,
    requested_model: str | None,
    effective_model: str | None,
    requested_effort: str | None,
    effective_effort: str | None,
    reason: str = "",
    runtime: str = "",
    origen_model: str = "",
    origen_effort: str = "",
    effort_effective_now: bool = False,
) -> dict:
    """Qué pidió el operador vs qué se ejecutó realmente, en los 3 runtimes.

    `downgraded` sólo mira lo que el operador pidió EXPLÍCITAMENTE: si no
    eligió modelo, que el router elija no es una degradación, es su trabajo.
    Ninguna clave existente se pierde (downgraded/reason): sólo se agregan
    `tool`, `effort_mode`, `effort_effective_now`, `origen_model`,
    `origen_effort`.
    """
    degradado = bool(
        (requested_model and effective_model != requested_model)
        or (requested_effort and effective_effort != requested_effort)
    )
    return {
        "tool": runtime,
        "requested_model": requested_model or "",
        "effective_model": effective_model or "",
        "requested_effort": requested_effort or "",
        "effective_effort": effective_effort or "",
        "downgraded": degradado,
        "reason": reason,
        "effort_mode": EFFORT_MODE.get(runtime, "no_aplica"),
        "effort_effective_now": bool(effort_effective_now),
        "origen_model": origen_model,
        "origen_effort": origen_effort,
    }


def _persist_model_effort_trace(execution_id: int, trace: dict) -> None:
    """Fusiona la traza en metadata_json. Nunca rompe el run (es informativo).

    `metadata_json` es una columna Text: se lee con el accessor y se escribe
    con json.dumps — asignarle un dict la dejaría como feature muerta
    silenciosa.
    """
    try:
        import json as _json

        from db import session_scope
        from models import AgentExecution

        with session_scope() as session:
            ex = session.query(AgentExecution).filter_by(id=execution_id).first()
            if not ex:
                return
            meta = dict(ex.metadata_dict or {})
            meta["model_effort"] = trace
            ex.metadata_json = _json.dumps(meta, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("stacky.services.runtime_capabilities").warning(
            "no se pudo persistir model_effort (no bloquea el run)", exc_info=True
        )
