"""Plan 269 F1 — colectores de evidencia. SOLO LECTURA, con tope de tiempo.

Rieles duros:
- No escribe, no crea, no borra, no mueve. Ni una fila, ni un archivo.
- Sin red: no llama a la API de ADO ni de GitLab. La evidencia de publicación
  sale de la tabla local `agent_html_publish`, que ya es el registro de lo que
  Stacky publicó (services/ado_publisher.py:122).
- Sin N+1: `collect_for_executions` resuelve TODO el lote con queries fijas.
- Ante cualquier fallo la señal queda en None (desconocida), NUNCA en False y
  NUNCA en True. Un colector jamás rompe el listado que lo llama.
- Sin autonomía: nadie lo llama en un loop. Se invoca cuando el operador ya
  estaba pidiendo el listado.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from services.run_verdict import EvidenceSignals

logger = logging.getLogger("stacky_agents.services.run_evidence")

COLLECTOR_BUDGET_S = 2.0   # presupuesto TOTAL del lote para las lecturas de disco

# `idempotent_replay` CUENTA como publicado: el dedupe detectó que el comentario
# ya estaba y por eso no volvió a llamar a ADO. El dedupe pre-ADO es por
# (ado_id, sha256, status='ok') (ado_publisher.py:392), así que la fila 'ok'
# queda pegada a la PRIMERA ejecución y toda re-corrida del mismo contenido solo
# tiene una fila 'idempotent_replay'. Filtrar solo 'ok' le habría dado False (no
# None) a esa re-corrida: perdía los 2 puntos de la señal MÁS PESADA y, por P2,
# False es peor que None ⇒ el falso_rojo_probable degradaba a error_real. Es
# decir: filtrar 'ok' reintroduce, dentro del colector, el falso rojo que este
# plan existe para matar — y justo en el caso más frecuente.
# NO se cuentan 'failed' ni 'skipped': ahí no hay comentario publicado.
PUBLISHED_STATUSES = ("ok", "idempotent_replay")


class _SidecarUnreadable(Exception):
    """No se pudo leer el sidecar ⇒ señal None (desconocida), nunca False."""


class _Budget:
    """Presupuesto TOTAL del lote, no por fila. Un lote de 200 ejecuciones no
    puede gastar 200 x timeout. Se consulta antes de CADA lectura de disco;
    agotado ⇒ la señal queda None (desconocida) y se sigue."""

    def __init__(self, seconds: float):
        self._deadline = time.monotonic() + float(seconds)

    def exhausted(self) -> bool:
        return time.monotonic() >= self._deadline


def collectors_enabled() -> bool:
    """STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED (default True). Lee la INSTANCIA."""
    import config as _config  # noqa: PLC0415

    return bool(getattr(_config.config, "STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED", True))


def _sidecar_path(execution_id: int) -> Path:
    """Misma ruta que services/incident_dev_pr.py:192-200, SIN mkdir.

    PROHIBIDO reusar el lector de intents de ese módulo: su cadena llama a
    `_intent_dir()`, que hace mkdir(parents=True, exist_ok=True) y por lo tanto
    CREA UN DIRECTORIO EN DISCO, violando el riel P4 ("ningún colector escribe,
    crea, mueve ni borra"). Además ese mkdir y su `is_file()` están FUERA del
    try, así que sí puede lanzar. Un centinela del plan exige 0 menciones del
    nombre de ese getter en este archivo, así que no se lo nombra.
    """
    from runtime_paths import data_dir  # noqa: PLC0415

    return data_dir() / "incident_dev_pr" / f"{int(execution_id)}.json"


def _read_sidecar(execution_id: int) -> dict | None:
    p = _sidecar_path(execution_id)
    try:
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _SidecarUnreadable(str(exc)) from exc


def _publish_ok_execution_ids(session, execution_ids: list[int]) -> set[int]:
    """UNA query para todo el lote (patrón api/executions.py:48-53)."""
    if not execution_ids:
        return set()
    from services.ado_publisher import AgentHtmlPublish  # noqa: PLC0415

    filas = (
        session.query(AgentHtmlPublish.execution_id)
        .filter(AgentHtmlPublish.execution_id.in_(execution_ids))
        .filter(AgentHtmlPublish.status.in_(PUBLISHED_STATUSES))
        .all()
    )
    return {int(f[0]) for f in filas if f[0] is not None}


def _gate_signal(ex) -> bool | None:
    """H1 declarada: se aceptan las DOS formas conocidas y nada más.

    Una tercera forma devuelve False (ausencia informada), nunca True.
    """
    try:
        cr = ex.contract_result          # property, models.py:309
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(cr, dict):
        return None                      # no hubo contrato: no se afirma nada
    if cr.get("passed") is True or cr.get("status") == "passed":
        return True
    return False


def _verification_signal(ex) -> bool | None:
    """El campo es `passed`, NO `ok` (services/exec_verification.py:70).

    `passed is None` es literalmente "could-not-verify" según el propio
    productor: mapea 1:1 a la señal desconocida del 269.
    """
    try:
        meta = ex.metadata_dict          # property, models.py:301
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(meta, dict):
        return None
    v = meta.get("exec_verification")
    if not isinstance(v, dict):
        return None                      # no corrió la verificación
    passed = v.get("passed")
    if passed is True:
        return True
    if passed is False:
        return False
    return None                          # could-not-verify o campo ausente


def _deliverable_signal(ex, presupuesto: _Budget) -> bool | None:
    salida = getattr(ex, "output", None)
    if isinstance(salida, str) and salida.strip():
        return True                      # sin tocar el disco
    ruta = getattr(ex, "html_output_path", None)
    if not (isinstance(ruta, str) and ruta.strip()):
        return False                     # no hay output ni ruta: ausencia informada
    if presupuesto.exhausted():
        return None                      # no se toca el disco: desconocida
    try:
        p = Path(ruta)
        if not p.is_file():
            return False
        return p.stat().st_size > 0
    except OSError:
        return None


def _repo_signal(ex, presupuesto: _Budget) -> bool | None:
    if presupuesto.exhausted():
        return None
    try:
        intent = _read_sidecar(int(getattr(ex, "id", 0) or 0))
    except _SidecarUnreadable:
        return None                      # no se pudo mirar
    except Exception:  # noqa: BLE001
        return None
    if intent is None:
        return False                     # este agente no toca repo: ausencia informada
    if not isinstance(intent, dict):
        return False
    if intent.get("pr_url") or intent.get("pr_id"):
        return True
    try:
        if int(intent.get("files_committed") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def _signals_from_execution(ex, *, publicado: bool | None, presupuesto: _Budget) -> EvidenceSignals:
    return EvidenceSignals(
        publicado_en_tracker=publicado,
        cambio_en_repo=_repo_signal(ex, presupuesto),
        gate_aceptacion_ok=_gate_signal(ex),
        verificacion_ok=_verification_signal(ex),
        entregable_presente=_deliverable_signal(ex, presupuesto),
    )


def collect_for_executions(session, executions: list) -> dict[int, EvidenceSignals]:
    """{execution_id: EvidenceSignals}. Con la flag OFF devuelve {} sin tocar nada.

    NUNCA lanza: cualquier fallo deja la señal en None y el listado sigue.
    """
    if not collectors_enabled():
        return {}
    if not executions:
        return {}

    ids = [int(ex.id) for ex in executions if getattr(ex, "id", None) is not None]
    try:
        publicados = _publish_ok_execution_ids(session, ids)
        publicado_por_id: dict[int, bool | None] = {i: (i in publicados) for i in ids}
    except Exception:  # noqa: BLE001 — la query falló: DESCONOCIDA, no False
        logger.debug("run_evidence: la query de publicacion fallo", exc_info=True)
        publicado_por_id = {i: None for i in ids}

    presupuesto = _Budget(COLLECTOR_BUDGET_S)
    out: dict[int, EvidenceSignals] = {}
    for ex in executions:
        ex_id = getattr(ex, "id", None)
        if ex_id is None:
            continue
        try:
            out[int(ex_id)] = _signals_from_execution(
                ex, publicado=publicado_por_id.get(int(ex_id)), presupuesto=presupuesto,
            )
        except Exception:  # noqa: BLE001
            logger.debug("run_evidence: fila %s fallo entera", ex_id, exc_info=True)
            out[int(ex_id)] = EvidenceSignals()
    return out
