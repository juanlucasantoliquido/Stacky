"""hot_recovery.py — Plan 262 F7. El orquestador de los 6 pasos del operador.

Ejecuta el orden exigido: capturar y registrar la ruta usada, validarla contra las
rutas permitidas, comprobar disponibilidad contra una direccion ESTABLE (nunca
contra la ruta que fallo), y recien ahi decidir. Reintenta SOLO el caso afectado y
deja correr el resto.

LIMITE DECLARADO: la granularidad real del reintento es el spec. Un paso de
asercion no tiene identidad direccionable desde Python (el compilador de escenarios
produce dicts planos y la numeracion es posicional), asi que reintentar un paso
suelto es inalcanzable sin rediseniar esa cadena. Esta escrito en el plan, en su
seccion de alcance y aca.

recover() NO se llama a si misma. Si el reintento vuelve a fallar, decide el
llamador y el presupuesto corta. Recursion aca seria un bucle infinito con nombre
elegante.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import agenda_health
import recovery_budget
import recovery_classifier
import route_allowlist

logger = logging.getLogger("stacky.qa_uat.hot_recovery")

_RUTA_DESCONOCIDA = "<desconocida>"


@dataclass(frozen=True)
class RecoveryOutcome:
    attempted: bool
    succeeded: bool
    recovery_class: str
    actions: tuple            # ("probe","return_to_safe_route","reauth","start_service","retry_case")
    verdict: object           # RecoveryVerdict de F3
    attempts: int             # intentos consumidos por ESTE caso hasta ahora
    final_reason: str         # "" si succeeded; el motivo si no
    route_used: str
    retried_result: dict | None = None   # F7.2 — transporta el dict del reintento
    safe_target: str = ""
    corrected_route: str = ""
    exception_text: str = ""

    def as_report(self) -> dict:
        """F10.2 — el bloque `recovery_report` del caso.

        None esta PROHIBIDO en route_used, exception, attempts y final_reason: un
        campo vacio en un diagnostico obliga al operador a adivinar, que es el
        pecado que el plan 241 corrigio agregando el traceback.
        """
        v = self.verdict
        health = getattr(v, "health", None)
        return {
            "route_used":     self.route_used or _RUTA_DESCONOCIDA,
            "exception":      self.exception_text or "",
            "exception_type": (self.exception_text.split(":", 1)[0]
                               if self.exception_text else ""),
            "attempts":       int(self.attempts or 0),
            "final_reason":   self.final_reason or "sin_motivo_registrado",
            "recovery_class": self.recovery_class or "UNRECOVERABLE",
            "route_allowed":  getattr(v, "route_allowed", None),
            "app_alive":      (None if health is None
                               else bool(getattr(health, "alive", False))),
            "actions_taken":  list(self.actions),
            "safe_route":     self.safe_target or "",
            "evidence":       getattr(v, "evidence", "") or "",
            "health_source":  getattr(health, "source", "") if health else "",
            "health_samples": int(getattr(health, "samples", 0) or 0) if health else 0,
        }


def build_budget_for_run():
    """Alias fino de recovery_budget.build_budget(), para que el call site de F7.2
    no tenga que importar dos modulos."""
    return recovery_budget.build_budget()


def _emit(exec_log, nombre: str, data: dict) -> None:
    """La recuperacion NO depende del logger: sin el, se omite en silencio."""
    if exec_log is None:
        return
    try:
        exec_log.event(nombre, data)
    except Exception:                              # noqa: BLE001
        pass


def _iter_execution_events(evidence_out) -> list:
    """Lee el execution.jsonl del run. NUNCA levanta: sin dato, lista vacia."""
    eventos: list = []
    if not evidence_out:
        return eventos
    try:
        raiz = Path(evidence_out)
        if not raiz.exists():
            return eventos
        for jsonl in raiz.rglob("execution.jsonl"):
            try:
                for linea in jsonl.read_text(encoding="utf-8").splitlines():
                    linea = linea.strip()
                    if not linea:
                        continue
                    try:
                        eventos.append(json.loads(linea))
                    except Exception:              # noqa: BLE001
                        continue
            except Exception:                      # noqa: BLE001
                continue
    except Exception:                              # noqa: BLE001
        return eventos
    return eventos


def route_of_case(run_dict: dict, evidence_out=None) -> str:
    """Ultima URL conocida del caso. Precedencia determinista. NUNCA levanta."""
    try:
        scenario = str((run_dict or {}).get("scenario_id") or "")
        for ev in reversed(_iter_execution_events(evidence_out)):
            data = ev.get("data") if isinstance(ev.get("data"), dict) else ev
            if scenario and str(data.get("scenario_id") or
                                ev.get("scenario_id") or "") != scenario:
                continue
            for clave in ("url_after", "url_before"):
                valor = data.get(clave)
                if valor:
                    return str(valor)
        return ""
    except Exception:                              # noqa: BLE001
        return ""


def nav_code_of_case(run_dict: dict, evidence_out=None) -> str | None:
    """Ultimo codigo de navegacion conocido del caso. NUNCA levanta."""
    try:
        scenario = str((run_dict or {}).get("scenario_id") or "")
        for ev in reversed(_iter_execution_events(evidence_out)):
            data = ev.get("data") if isinstance(ev.get("data"), dict) else ev
            if scenario and str(data.get("scenario_id") or
                                ev.get("scenario_id") or "") != scenario:
                continue
            for clave in ("error_code", "nav_code"):
                valor = data.get(clave)
                if valor and str(valor) in recovery_classifier._NAV_CODE_TO_CLASS:
                    return str(valor)
        return None
    except Exception:                              # noqa: BLE001
        return None


def retry_case(*, spec_file, scenario_id: str, scenario_dir, ticket_id: int,
               headed: bool, timeout_ms: int, verbose: bool, exec_log=None) -> dict:
    """Reintento acotado al caso. Cablea codigo que ya existia y estaba MUERTO."""
    import uat_test_runner
    return uat_test_runner.run_single_spec(
        spec_file=spec_file, scenario_id=scenario_id, scenario_dir=scenario_dir,
        ticket_id=ticket_id, headed=headed, timeout_ms=timeout_ms,
        verbose=verbose, exec_log=exec_log,
    )


def _autostart_permitido() -> bool:
    """Reusa la flag del plan 240: arrancar un proceso en la maquina del operador
    es EL MISMO acto que esa flag ya gatea. Crear una segunda seria duplicar el
    gate del 240 y romper la frontera declarada entre los dos planes."""
    import os
    return os.environ.get("STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED",
                          "true").strip().lower() in ("1", "true", "yes", "si", "on")


def _reintentar(run_dict, evidence_out, exec_log, acciones: list):
    """Devuelve (dict_del_reintento | None, ok). Una excepcion NO puede escalar:
    seria el bug original con un paso extra."""
    if not run_dict:
        return None, False
    try:
        spec_file = Path(str(run_dict.get("spec_file") or ""))
        scenario_id = str(run_dict.get("scenario_id") or "")
        scenario_dir = Path(evidence_out) / scenario_id if evidence_out else spec_file.parent
        acciones.append("retry_case")
        resultado = retry_case(
            spec_file=spec_file, scenario_id=scenario_id, scenario_dir=scenario_dir,
            ticket_id=int(run_dict.get("ticket_id") or 0), headed=False,
            timeout_ms=int(run_dict.get("timeout_ms") or 30_000),
            verbose=False, exec_log=exec_log,
        )
        # F10.1 — un caso que pasa DESPUES de un reintento no es un exito limpio:
        # es una senal honesta de inestabilidad. Se emite con el metodo que ya
        # existe para esto, no con uno nuevo.
        if (resultado or {}).get("status") == "pass" and exec_log is not None:
            try:
                exec_log.flake_suspected(
                    test_id=scenario_id, reason="PASS_ON_RETRY", attempt=1,
                    metadata={"origen": "plan_262_hot_recovery"},
                )
            except Exception:                      # noqa: BLE001
                pass
        return resultado, bool(resultado)
    except Exception:                              # noqa: BLE001
        logger.warning("el reintento del caso fallo", exc_info=True)
        return None, False


def recover(*, case_id: str, exc: BaseException | None = None, exc_text: str = "",
            route_used: str = "", nav_code: str | None = None,
            budget=None, exec_log=None, run_dict=None,
            evidence_out=None) -> RecoveryOutcome:
    """Los 6 pasos del operador, en orden. NUNCA levanta.

    `run_dict` y `evidence_out` son necesarios para poder reintentar el caso: son
    el unico lugar de donde salen el spec y su carpeta de evidencia. El plan
    declaraba el reintento sin nombrar de donde venia el spec.
    """
    if budget is None:
        budget = build_budget_for_run()

    texto = (exc_text or "").strip()
    if not texto and exc is not None:
        texto = f"{type(exc).__name__}: {exc}"
    ruta = (route_used or "").strip()
    acciones: list = []

    # ── PASO 1 — CAPTURAR Y REGISTRAR LA RUTA USADA, antes de decidir nada ────
    _emit(exec_log, "recovery_attempt_start", {
        "case_id": case_id, "route_used": ruta or _RUTA_DESCONOCIDA,
        "exc_type": (type(exc).__name__ if exc is not None
                     else (texto.split(":", 1)[0] if texto else "")),
        "nav_code": nav_code,
    })

    # ── PASO 2 — VERIFICAR LA RUTA CONTRA LAS RUTAS PERMITIDAS ───────────────
    try:
        rv = route_allowlist.is_allowed(ruta)
        route_allowed = rv.allowed
    except Exception:                              # noqa: BLE001
        route_allowed = None

    # ── PASO 3 — COMPROBAR DISPONIBILIDAD CONTRA UNA URL ESTABLE (INV-5) ─────
    acciones.append("probe")
    try:
        health = agenda_health.probe_agenda_confirmed()
    except Exception:                              # noqa: BLE001
        health = None
    _emit(exec_log, "recovery_health_probe", {
        "url": getattr(health, "url", ""), "alive": getattr(health, "alive", None),
        "status": getattr(health, "status", None),
        "elapsed_ms": getattr(health, "elapsed_ms", 0),
        "error": getattr(health, "error", ""),
        "source": getattr(health, "source", ""),
        "samples": getattr(health, "samples", 0),
    })

    verdict = recovery_classifier.classify_recovery(
        exc=exc, exc_text=texto, route_used=ruta, nav_code=nav_code,
        health=health, route_allowed=route_allowed)
    clase = verdict.recovery_class
    _emit(exec_log, "recovery_classified", {
        "recovery_class": clase, "reason_code": verdict.reason_code,
        "route_allowed": route_allowed, "evidence": verdict.evidence,
    })

    def _salida(attempted, succeeded, final_reason, retried=None,
                safe_target="", corrected=""):
        _emit(exec_log, "recovery_outcome", {
            "succeeded": succeeded, "attempts": budget.attempts_for(case_id),
            "final_reason": final_reason, "route_used": ruta or _RUTA_DESCONOCIDA,
        })
        return RecoveryOutcome(
            attempted=attempted, succeeded=succeeded, recovery_class=clase,
            actions=tuple(acciones), verdict=verdict,
            attempts=budget.attempts_for(case_id), final_reason=final_reason,
            route_used=ruta or _RUTA_DESCONOCIDA, retried_result=retried,
            safe_target=safe_target, corrected_route=corrected,
            exception_text=texto,
        )

    ok, why = budget.can_recover(case_id, clase)
    if not ok:
        # Incluye INV-2: FUNCTIONAL_ERROR da "clase_no_recuperable" y NO se reintenta.
        budget.consume(case_id, clase, detail=verdict.evidence)
        motivo = ("error_funcional_no_se_recupera"
                  if clase == recovery_classifier.FUNCTIONAL_ERROR else why)
        _emit(exec_log, "recovery_budget_state", _budget_state(budget, case_id))
        return _salida(False, False, motivo)

    # ── PASO 5 — SI NO RESPONDE ──────────────────────────────────────────────
    if clase == recovery_classifier.SERVICE_DOWN:
        if not _autostart_permitido():
            _emit(exec_log, "recovery_action",
                  {"action": "start_service", "target": "", "ok": False})
            return _salida(False, False, "autostart_deshabilitado")
        acciones.append("start_service")
        try:
            import agenda_web_launcher
            resultado = agenda_web_launcher.ensure_agenda_web(
                base_url=route_allowlist._base_url())
        except Exception:                          # noqa: BLE001
            resultado = {"ok": False}
        _emit(exec_log, "recovery_action", {
            "action": "start_service", "target": route_allowlist._base_url(),
            "ok": bool((resultado or {}).get("ok")),
        })
        budget.consume(case_id, clase, detail="arranque de servicio")
        _emit(exec_log, "recovery_budget_state", _budget_state(budget, case_id))
        # ensure_agenda_web ya hace polling de 1s hasta timeout: NO se agrega un
        # segundo bucle de espera.
        try:
            revivio = agenda_health.probe_agenda().alive
        except Exception:                          # noqa: BLE001
            revivio = False
        if not revivio:
            return _salida(True, False, "la aplicacion no revivio tras el arranque")
        destino = _destino_seguro(acciones)
        retried, ok_retry = _reintentar(run_dict, evidence_out, exec_log, acciones)
        return _salida(True, ok_retry,
                       "" if ok_retry else "el reintento no produjo resultado",
                       retried=retried, safe_target=destino)

    # ── PASO 4 — SI RESPONDE ─────────────────────────────────────────────────
    if clase == recovery_classifier.SESSION_ERROR:
        # PROHIBIDO llamar run_auth_session desde aca: es sincrona y el plan 240 C1
        # ya lo probo. Sin un `page` de Playwright, la reautenticacion se DELEGA al
        # reintento: el spec vuelve a loguearse por su cuenta.
        acciones.append("reauth")
        _emit(exec_log, "recovery_action",
              {"action": "reauth", "target": "delegado_al_reintento", "ok": True})

    destino = _destino_seguro(acciones)
    corregida = _ruta_corregida(ruta, route_allowed)
    _emit(exec_log, "recovery_action",
          {"action": "return_to_safe_route", "target": destino, "ok": True})

    budget.consume(case_id, clase, detail=verdict.evidence)
    _emit(exec_log, "recovery_budget_state", _budget_state(budget, case_id))
    retried, ok_retry = _reintentar(run_dict, evidence_out, exec_log, acciones)
    return _salida(True, ok_retry,
                   "" if ok_retry else "el reintento no produjo resultado",
                   retried=retried, safe_target=destino, corrected=corregida)


def _budget_state(budget, case_id) -> dict:
    return {
        "used_run": budget._used_run, "max_run": budget.max_per_run,
        "used_case": budget.attempts_for(case_id), "max_case": budget.max_per_case,
        "service_starts": budget._service_starts,
    }


def _destino_seguro(acciones: list) -> str:
    """La ruta segura, salvo que sea una pantalla hija: esas no admiten goto()
    directo y un goto() a una de ellas produce NAV_DEVIATION garantizado."""
    acciones.append("return_to_safe_route")
    try:
        destino = route_allowlist.safe_route_url()
        if route_allowlist.is_child_screen(destino):
            return route_allowlist._base_url()
        return destino
    except Exception:                              # noqa: BLE001
        return ""


def _ruta_corregida(ruta: str, route_allowed) -> str:
    """Match EXACTO por nombre de archivo, case-insensitive. SIN fuzzy: un match
    aproximado navega a la pantalla equivocada y produce un verde falso (INV-1)."""
    try:
        if route_allowed is not False:
            return ""
        rutas, _ = route_allowlist.effective_allowlist()
        objetivo = route_allowlist.normalize_route(ruta).rsplit("/", 1)[-1].lower()
        for candidata in rutas:
            if candidata.rsplit("/", 1)[-1].lower() == objetivo:
                return candidata
        return route_allowlist.safe_route_url()
    except Exception:                              # noqa: BLE001
        return ""
