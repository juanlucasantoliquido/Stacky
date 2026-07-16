"""services/integration_breaker.py — Circuit-breaker persistido para integraciones
no configuradas / caídas (auditoría 2026-07-15: V3 PAT ADO, V8 Jira, D6 LLM/ADO).

Persistido en data_dir()/integration_breaker.json para sobrevivir restarts (el
grueso de los ~941 warnings de V3 viene de re-arranques de proceso + create_app()
de pytest, no de un único daemon). Runtime-agnóstico: nada que ver con el runner
de agentes. NUNCA lanza: ante cualquier problema de IO degrada a "cerrado".
"""
from __future__ import annotations
import json, logging, time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from runtime_paths import data_dir

logger = logging.getLogger("stacky_agents.integration_breaker")

_FILENAME = "integration_breaker.json"

# Backoff: al abrir por fallo terminal de config, no reintentar por esta ventana.
# Constante interna (no perilla del operador en v1).
_BACKOFF_BASE_SEC = 15 * 60          # 15 min tras la 1ª apertura
_BACKOFF_MAX_SEC  = 6 * 60 * 60      # tope 6 h

# Razones (machine-readable). Manejan la copy de la UI y el mensaje de degradación.
REASON_PAT_EXPIRED        = "ado_pat_expired"
REASON_ADO_PROJECT_MISSING= "ado_project_not_found"
REASON_JIRA_NOT_CONFIGURED= "jira_not_configured"
REASON_LOCAL_LLM_DOWN     = "local_llm_unavailable"
REASON_ADO_IDENTITY_UNRESOLVED = "ado_identity_unresolved"
REASON_UNKNOWN            = "unknown"

def _now() -> float: return time.time()
def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def integration_key(integration: str, project: str | None) -> str:
    return f"{integration}::{(project or '').upper()}"

def ado_breaker_project(project_name: str | None) -> str | None:
    """[C3] Única derivación de la parte 'project' de la key para integraciones ADO.
    TODOS los productores/consumidores del breaker ADO (should_skip en _startup_sync,
    record_failure en _ado_sync_error_response y en get_ado_user) DEBEN usar esto para
    que la key coincida (si no, should_skip nunca matchea lo que abrió record_failure).
    Resuelve el tracker_project real del contexto y cae al nombre crudo si no hay ctx.
    NUNCA lanza."""
    try:
        from services.project_context import resolve_project_context
        ctx = resolve_project_context(project_name=project_name)
        tp = (ctx.tracker_project if ctx else None) or project_name
    except Exception:
        tp = project_name
    return (tp or "").strip() or None

def _path() -> Path: return data_dir() / _FILENAME
def _load() -> dict:
    p = _path()
    if not p.exists(): return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"));  return d if isinstance(d, dict) else {}
    except Exception: return {}
def _save(d: dict) -> None:
    try:
        p = _path(); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.debug("integration_breaker: no se pudo persistir (degrado a memoria)", exc_info=True)

@dataclass(frozen=True)
class BreakerState:
    open: bool
    reason: str
    message: str
    fail_count: int
    opened_at: str | None
    retry_after: str | None
    seconds_until_retry: int   # 0 si cerrado o si ya pasó la ventana

def should_skip(integration: str, project: str | None) -> bool:
    """True = breaker abierto Y todavía dentro de la ventana de backoff → NO golpear la red."""
    e = _load().get(integration_key(integration, project))
    if not e or not e.get("open"): return False
    return _now() < float(e.get("retry_after_ts") or 0)

def record_failure(integration: str, project: str | None, reason: str, message: str) -> BreakerState:
    """Registra un fallo terminal de config: abre el breaker con backoff exponencial.
    Loguea WARNING SOLO en la transición cerrado→abierto (dedup); mientras siga
    abierto, DEBUG. Devuelve el estado resultante."""
    d = _load(); k = integration_key(integration, project)
    prev = d.get(k) or {}
    was_open = bool(prev.get("open"))
    fail_count = int(prev.get("fail_count") or 0) + 1
    backoff = min(_BACKOFF_BASE_SEC * (2 ** max(0, fail_count - 1)), _BACKOFF_MAX_SEC)
    now = _now(); retry_ts = now + backoff
    d[k] = {"open": True, "reason": reason, "message": message[:500], "fail_count": fail_count,
            "opened_at": prev.get("opened_at") or _iso(now), "opened_at_ts": prev.get("opened_at_ts") or now,
            "retry_after": _iso(retry_ts), "retry_after_ts": retry_ts,
            "last_error_at": _iso(now)}
    _save(d)
    if not was_open:
        logger.warning("integración '%s' (proyecto=%s) DESACTIVADA por %s: %s — reintento tras %s",
                       integration, project or "-", reason, message[:200], _iso(retry_ts))
    else:
        logger.debug("integración '%s' sigue abierta (fail_count=%d)", integration, fail_count)
    return get_state(integration, project)

def record_success(integration: str, project: str | None) -> None:
    """Cierra el breaker (reset) al primer éxito. Loguea INFO solo si venía abierto."""
    d = _load(); k = integration_key(integration, project)
    if d.get(k, {}).get("open"):
        logger.info("integración '%s' (proyecto=%s) RESTABLECIDA", integration, project or "-")
    if k in d: d.pop(k, None); _save(d)

def reset(integration: str, project: str | None) -> None:
    """Cierre manual (acción del operador: 'Reintentar ahora' / renovó credencial)."""
    d = _load(); k = integration_key(integration, project)
    if k in d: d.pop(k, None); _save(d)

def get_state(integration: str, project: str | None) -> BreakerState:
    e = _load().get(integration_key(integration, project))
    if not e or not e.get("open"):
        return BreakerState(False, "", "", 0, None, None, 0)
    retry_ts = float(e.get("retry_after_ts") or 0)
    return BreakerState(True, e.get("reason") or REASON_UNKNOWN, e.get("message") or "",
                        int(e.get("fail_count") or 0), e.get("opened_at"), e.get("retry_after"),
                        max(0, int(retry_ts - _now())))

def all_states() -> dict[str, BreakerState]:
    # [C6] Guardar contra keys malformadas en el JSON (invariante "NUNCA lanza"):
    # partition siempre devuelve 3 partes; get_state acepta ("", ...) sin romper.
    out: dict[str, BreakerState] = {}
    for k in _load().keys():
        integ, _sep, proj = k.partition("::")
        try:
            out[k] = get_state(integ, proj or None)
        except Exception:
            logger.debug("integration_breaker: key malformada ignorada: %r", k, exc_info=True)
    return out


def classify_ado_error(exc) -> tuple[str, str]:
    """(reason, message) a partir de un AdoApiError. Substrings verificados contra
    los mensajes reales del reporte (V3/D9)."""
    msg = str(getattr(exc, "detail", "") or "") + " " + str(exc)
    low = msg.lower()
    if "personal access token used has expired" in low or "access denied" in low:
        return REASON_PAT_EXPIRED, "El PAT de Azure DevOps expiró. Renovalo en la Caja Fuerte."
    if "does not exist" in low and "project" in low:
        return REASON_ADO_PROJECT_MISSING, "El proyecto ADO configurado no existe. Revisá el nombre en la config del proyecto."
    if getattr(exc, "status_code", None) in (401, 403):
        return REASON_PAT_EXPIRED, "ADO rechazó el PAT (401/403). Renovalo en la Caja Fuerte."
    return REASON_UNKNOWN, str(exc)[:200]
