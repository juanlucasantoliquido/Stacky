"""Plan 262 F7.1 — hot_recovery: el orquestador de los 6 pasos del operador.

18 casos, TODO mockeado: cero red y cero navegador.

Tres gates atacan las tres formas de hacerlo mal:
  - test_paso3_prueba_la_base_no_la_ruta_rota mata la implementacion intuitiva
    (preguntarle a la ruta rota si el servidor esta vivo).
  - test_app_viva_ruta_legal_funcional_no_reintenta mata la entusiasta
    (reintentar todo), que es la que produce verdes falsos.
  - test_session_error_no_llama_run_auth_session mata la regresion del 240 C1.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import agenda_health
import hot_recovery as hr
import recovery_budget as rb
import uat_test_runner
from agenda_health import HealthProbe

_TOOL_ROOT = Path(__file__).resolve().parents[2]
_BASE = "http://localhost:35017/AgendaWeb/"


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", _BASE)
    for k in ("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "STACKY_QA_UAT_ROUTE_ALLOWLIST",
              "STACKY_QA_UAT_SAFE_ROUTE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED", "true")


def _viva() -> HealthProbe:
    return HealthProbe(True, 200, _BASE, 5, "", "http_probe_confirmed", 2)


def _muerta() -> HealthProbe:
    return HealthProbe(False, None, _BASE, 5000, "URLError: refused",
                       "http_probe_confirmed", 2)


class _FakeLog:
    def __init__(self):
        self.eventos = []

    def event(self, event_name, data, **kw):
        self.eventos.append((event_name, data))


def _run_dict(status="fail", scenario_id="esc1"):
    return {"scenario_id": scenario_id, "spec_file": str(_TOOL_ROOT / "x.spec.ts"),
            "status": status, "reason": "", "raw_stderr": "boom"}


# ── PASO 1 y 3 ────────────────────────────────────────────────────────────────

def test_paso1_registra_la_ruta_antes_de_decidir():
    """Si el proceso muere aca, el operador igual sabe cual era la ruta."""
    log = _FakeLog()
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()):
        hr.recover(case_id="esc1", exc_text="boom", route_used="FrmRota.aspx",
                   budget=rb.RecoveryBudget(6, 1, 1), exec_log=log,
                   run_dict=_run_dict())
    assert log.eventos, "no se registro ningun evento"
    nombre, data = log.eventos[0]
    assert nombre == "recovery_attempt_start"
    assert data.get("route_used") == "FrmRota.aspx"


def test_paso3_prueba_la_base_no_la_ruta_rota():
    """INV-5. Preguntarle a la ruta rota si el servidor esta vivo ES el bug."""
    with patch.object(agenda_health, "probe_agenda_confirmed",
                      return_value=_viva()) as probe:
        hr.recover(case_id="esc1", exc_text="boom",
                   route_used="FrmRotaInexistente.aspx",
                   budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert probe.called
    llamada = f"{probe.call_args.args} {probe.call_args.kwargs}"
    assert "FrmRotaInexistente.aspx" not in llamada, (
        f"el probe se hizo contra la ruta que fallo: {llamada}"
    )


# ── PASO 4: la app responde ───────────────────────────────────────────────────

def test_app_viva_ruta_mala_vuelve_a_ruta_segura(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_ROUTE_ALLOWLIST", "FrmLogin.aspx")
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         return_value=_run_dict(status="pass")):
        out = hr.recover(case_id="esc1", exc_text="boom", route_used="FrmMala.aspx",
                         budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert "return_to_safe_route" in out.actions, out.actions


def test_app_viva_ruta_mala_reintenta_solo_el_caso(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_ROUTE_ALLOWLIST", "FrmLogin.aspx")
    rd = _run_dict()
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         return_value=_run_dict(status="pass")) as spec:
        out = hr.recover(case_id="esc1", exc_text="boom", route_used="FrmMala.aspx",
                         budget=rb.RecoveryBudget(6, 1, 1), run_dict=rd)
    assert spec.call_count == 1, f"se esperaba 1 reintento, hubo {spec.call_count}"
    assert str(spec.call_args.kwargs.get("spec_file")) == rd["spec_file"]
    assert out.retried_result is not None


def test_app_viva_ruta_legal_funcional_no_reintenta():
    """GATE. INV-2: reintentar una asercion que fallo es la definicion de verde falso."""
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec") as spec:
        out = hr.recover(case_id="esc1", exc_text="expected 5 got 3",
                         route_used="FrmBusqueda.aspx",
                         budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert spec.call_count == 0, "un error funcional NO se reintenta"
    assert out.attempted is False
    assert out.recovery_class == "FUNCTIONAL_ERROR"


def test_session_error_reautentica():
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         return_value=_run_dict(status="pass")):
        out = hr.recover(case_id="esc1", exc_text="x", route_used="FrmBusqueda.aspx",
                         nav_code="NAV_SESSION_LOST",
                         budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert "reauth" in out.actions, out.actions


def test_session_error_no_llama_run_auth_session():
    """GATE DEL 240 C1: run_auth_session es SINCRONA y no se llama desde aca."""
    import auth_session_factory
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         return_value=_run_dict(status="pass")), \
            patch.object(auth_session_factory, "run_auth_session") as ras:
        hr.recover(case_id="esc1", exc_text="x", route_used="FrmBusqueda.aspx",
                   nav_code="NAV_SESSION_LOST",
                   budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert ras.call_count == 0, "run_auth_session no puede llamarse desde este camino"


# ── PASO 5: la app NO responde ────────────────────────────────────────────────

def test_app_caida_arranca_el_servicio():
    import agenda_web_launcher
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_muerta()), \
            patch.object(agenda_web_launcher, "ensure_agenda_web",
                         return_value={"ok": True, "started_by_us": True}) as ens, \
            patch.object(agenda_health, "probe_agenda", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         return_value=_run_dict(status="pass")):
        hr.recover(case_id="esc1", exc_text="boom", route_used="FrmBusqueda.aspx",
                   budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert ens.call_count == 1


def test_app_caida_con_flag_240_off_no_arranca(monkeypatch):
    """Arrancar un proceso en la maquina del operador ya tiene su gate en el 240."""
    monkeypatch.setenv("STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED", "false")
    import agenda_web_launcher
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_muerta()), \
            patch.object(agenda_web_launcher, "ensure_agenda_web") as ens:
        out = hr.recover(case_id="esc1", exc_text="boom", route_used="FrmBusqueda.aspx",
                         budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert ens.call_count == 0
    assert out.succeeded is False


def test_segundo_service_down_no_arranca_dos_veces():
    import agenda_web_launcher
    budget = rb.RecoveryBudget(6, 6, 1)
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_muerta()), \
            patch.object(agenda_web_launcher, "ensure_agenda_web",
                         return_value={"ok": True}) as ens, \
            patch.object(agenda_health, "probe_agenda", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         return_value=_run_dict(status="pass")):
        hr.recover(case_id="esc1", exc_text="b", route_used="a.aspx",
                   budget=budget, run_dict=_run_dict())
        hr.recover(case_id="esc2", exc_text="b", route_used="a.aspx",
                   budget=budget, run_dict=_run_dict())
    assert ens.call_count == 1, f"se arranco el servicio {ens.call_count} veces"


def test_app_no_revive_da_unrecoverable():
    import agenda_web_launcher
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_muerta()), \
            patch.object(agenda_web_launcher, "ensure_agenda_web",
                         return_value={"ok": False}), \
            patch.object(agenda_health, "probe_agenda", return_value=_muerta()):
        out = hr.recover(case_id="esc1", exc_text="boom", route_used="a.aspx",
                         budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert out.succeeded is False
    assert out.final_reason


# ── Presupuesto y bordes ──────────────────────────────────────────────────────

def test_presupuesto_agotado_no_intenta():
    budget = rb.RecoveryBudget(10, 1, 1)
    budget.consume("esc1", "ROUTE_ERROR")
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec") as spec:
        out = hr.recover(case_id="esc1", exc_text="x", route_used="FrmMala.aspx",
                         nav_code="NAV_DEVIATION", budget=budget, run_dict=_run_dict())
    assert out.attempted is False
    assert out.final_reason == "presupuesto_del_caso_agotado"
    assert spec.call_count == 0


def test_child_screen_como_ruta_segura_usa_la_base(monkeypatch):
    """Un goto() a una pantalla hija es NAV_DEVIATION garantizado."""
    monkeypatch.setenv("STACKY_QA_UAT_SAFE_ROUTE", "FrmDetalleClie.aspx")
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         return_value=_run_dict(status="pass")):
        out = hr.recover(case_id="esc1", exc_text="x", route_used="FrmMala.aspx",
                         nav_code="NAV_DEVIATION",
                         budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert out.safe_target == _BASE, (
        f"se intento volver a una pantalla hija: {out.safe_target}"
    )


def test_ruta_corregida_es_match_exacto_o_ruta_segura(monkeypatch):
    """SIN fuzzy: un match aproximado navega a la pantalla equivocada = verde falso."""
    monkeypatch.setenv("STACKY_QA_UAT_ROUTE_ALLOWLIST", "FrmBusqueda.aspx")
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         return_value=_run_dict(status="pass")):
        out = hr.recover(case_id="esc1", exc_text="x", route_used="FrmBusquedaX.aspx",
                         budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert out.corrected_route == hr.route_allowlist.safe_route_url(), (
        f"hubo fuzzy matching: {out.corrected_route}"
    )


def test_excepcion_en_el_reintento_no_escala():
    """Una excepcion en el reintento seria el bug original con un paso extra."""
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         side_effect=RuntimeError("boom en el reintento")):
        out = hr.recover(case_id="esc1", exc_text="x", route_used="FrmMala.aspx",
                         nav_code="NAV_DEVIATION",
                         budget=rb.RecoveryBudget(6, 1, 1), run_dict=_run_dict())
    assert out.succeeded is False
    assert out.attempted is True


def test_recover_no_es_recursiva():
    """Recursion en un recuperador es un bucle infinito con nombre elegante."""
    cuerpo = inspect.getsource(hr.recover)
    cuerpo = "\n".join(cuerpo.split("\n")[1:])       # sin la linea del def
    hits = re.findall(r"\brecover\s*\(", cuerpo)     # \b no matchea can_recover(
    assert hits == [], f"recover se llama a si misma {len(hits)} vez/veces"


def test_sin_exec_log_no_lanza():
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         return_value=_run_dict(status="pass")):
        out = hr.recover(case_id="esc1", exc_text="x", route_used="FrmMala.aspx",
                         nav_code="NAV_DEVIATION",
                         budget=rb.RecoveryBudget(6, 1, 1), exec_log=None,
                         run_dict=_run_dict())
    assert out is not None


def test_run_single_spec_tiene_alias_publico():
    """F7.2 cablea codigo que existia y estaba MUERTO (1 hit: su propia definicion)."""
    assert hasattr(uat_test_runner, "run_single_spec")
    assert uat_test_runner.run_single_spec is uat_test_runner._run_single_spec
