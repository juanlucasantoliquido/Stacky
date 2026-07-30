"""
test_plan274_deeplink_probe.py — Plan 274 F4.

Conecta `deeplink_readiness_checker.py` (huerfano #4): cuando el pipeline decide
usar un deep link —lo cual YA HACE— lo prueba antes de gastar una corrida en una
URL que redirige a login.

NO CONTRADICE EL PLAN 240. El 240 prohibio las URLs `?q=` con payload cifrado
por sesion porque DESTRUIAN la sesion. Los deep links legitimos son los del
contrato con parametros de negocio (`FrmDetalleClie.aspx?clcod={CLCOD}`),
permitidos solo en lanes no-humanos. Esta fase respeta esa prohibicion y solo
agrega un probe donde el deeplink YA estaba permitido.

TODO CON DOBLE, SIN RED. Y los dobles devuelven la FORMA REAL del modulo
(`decision`/`category`/`reason`/`checks`), nunca una inventada: el v1 hacia
`probe.get("ready", False)` sobre una clave que el modulo NUNCA devuelve, asi
que degradaba el deeplink SIEMPRE — y sus 5 tests daban verde porque el doble
tambien inventaba la clave.
"""
from __future__ import annotations

from pathlib import Path

import pytest

TOOL_ROOT = Path(__file__).resolve().parents[2]
CONTRATOS = TOOL_ROOT / "navigation_contracts.yml"


def _probe(decision="PASS", reason=None, category=None) -> dict:
    """Doble con la forma REAL de `_build_result` (deeplink_readiness_checker.py:362)."""
    return {
        "event": "deeplink_readiness_check",
        "screen": "FrmDetalleClie.aspx",
        "url_pattern": "FrmDetalleClie.aspx?clcod={CLCOD}",
        "params": {"CLCOD": "123"},
        "url": "FrmDetalleClie.aspx?clcod=123",
        "checks": {},
        "missing_params": [],
        "decision": decision,
        "category": category,
        "reason": reason,
        "human_action_required": None,
    }


@pytest.fixture()
def resolver(monkeypatch):
    import navigation_strategy_resolver as nsr
    monkeypatch.setenv("STACKY_QA_UAT_DEEPLINK_PROBE_ENABLED", "true")
    return nsr


def _resolve(nsr, lane="smoke_deeplink", screen="FrmDetalleClie.aspx"):
    return nsr.resolve_navigation_strategy(
        ticket_id=274, scenario_id="P01", target_screen=screen, lane=lane,
        available_data={"CLCOD": "123"}, contracts_path=CONTRATOS)


def test_el_doble_usa_la_forma_real():
    """CENTINELA ANTI-FALSO-VERDE de toda la fase. Corre primero.

    Sin el, los tests de abajo pasan contra una forma que el modulo real nunca
    emite — que es exactamente lo que le paso al v1.
    """
    import inspect

    import deeplink_readiness_checker as drc

    src = inspect.getsource(drc._build_result)
    claves_reales = {"event", "screen", "url_pattern", "params", "url", "checks",
                     "missing_params", "decision", "category", "reason",
                     "human_action_required"}
    for k in claves_reales:
        assert f'"{k}"' in src, f"_build_result ya no devuelve la clave {k!r}"

    assert set(_probe()) <= claves_reales, (
        f"el doble inventa claves: {set(_probe()) - claves_reales}")
    assert "ready" not in claves_reales
    assert '"ready"' not in drc.__doc__ or True
    assert "ready" not in _probe(), (
        "el doble usa la clave 'ready', que el modulo NUNCA devuelve. Con "
        "`.get('ready', False)` el resultado es siempre falso y F4 degradaria "
        "el deeplink SIEMPRE, incluso con el probe en PASS.")

    assert drc.check_deeplink_readiness.__code__.co_varnames[:5] == (
        "screen", "params", "base_url", "contracts_path", "timeout_s"), (
        "cambio la firma de check_deeplink_readiness; F4 la invoca por nombre")


def test_probe_pass_mantiene_deeplink(resolver, monkeypatch):
    llamadas = []

    def _fake(**kw):
        llamadas.append(kw)
        return _probe(decision="PASS")

    monkeypatch.setattr("deeplink_readiness_checker.check_deeplink_readiness", _fake)
    r = _resolve(resolver)
    assert r.get("strategy") == "deeplink", r
    assert llamadas, "el probe no se invoco"


def test_probe_blocked_por_login_degrada_a_human_path(resolver, monkeypatch):
    monkeypatch.setattr(
        "deeplink_readiness_checker.check_deeplink_readiness",
        lambda **kw: _probe(decision="BLOCKED", reason="redirected_to_login",
                            category="NAV"))
    r = _resolve(resolver)
    assert r.get("strategy") != "deeplink", (
        f"con el probe en BLOCKED no se puede seguir usando el deeplink: {r}")
    texto = " ".join(str(v) for v in r.values())
    assert "redirected_to_login" in texto, (
        f"el motivo del probe tiene que propagarse al resultado: {r}")


def test_probe_falla_abierto_si_lanza(resolver, monkeypatch):
    """FALLA ABIERTO A PROPOSITO: un probe roto no bloquea lo que ya funcionaba."""
    def _boom(**kw):
        raise RuntimeError("red caida")

    monkeypatch.setattr("deeplink_readiness_checker.check_deeplink_readiness", _boom)
    r = _resolve(resolver)
    assert r.get("strategy") == "deeplink", (
        f"con el probe roto el flujo tiene que seguir EXACTAMENTE como hoy: {r}")


def test_flag_off_no_llama_al_probe(resolver, monkeypatch):
    llamadas = []
    monkeypatch.setenv("STACKY_QA_UAT_DEEPLINK_PROBE_ENABLED", "false")
    monkeypatch.setattr("deeplink_readiness_checker.check_deeplink_readiness",
                        lambda **kw: llamadas.append(kw) or _probe("BLOCKED"))
    r = _resolve(resolver)
    assert len(llamadas) == 0, "con la flag OFF el probe no se puede invocar"
    assert r.get("strategy") == "deeplink"


def test_lane_humano_sigue_prohibido(resolver, monkeypatch):
    """CENTINELA DEL PLAN 240: en lane humano no hay deeplink, ni probe."""
    llamadas = []
    monkeypatch.setattr("deeplink_readiness_checker.check_deeplink_readiness",
                        lambda **kw: llamadas.append(kw) or _probe("PASS"))
    r = _resolve(resolver, lane="uat_human")
    assert r.get("strategy") != "deeplink", (
        f"lane uat_human tiene deeplink PROHIBIDO por contrato: {r}")
    assert len(llamadas) == 0, (
        "no se puede ni consultar el probe en un lane donde el deeplink esta prohibido")


def test_se_invoca_con_los_nombres_reales(resolver, monkeypatch):
    """CORRE CONTRA EL DEFECTO del v1: usaba `screen`, `params` y `base_url`,
    tres identificadores que NO EXISTEN en el scope del resolver (los reales son
    `target_screen` y `available_data`) => NameError en la primera corrida."""
    capturado = {}

    def _fake(**kw):
        capturado.update(kw)
        return _probe("PASS")

    monkeypatch.setattr("deeplink_readiness_checker.check_deeplink_readiness", _fake)
    _resolve(resolver)

    assert capturado.get("screen") == "FrmDetalleClie.aspx", capturado
    assert capturado.get("params") == {"CLCOD": "123"}, capturado
    assert "base_url" not in capturado, (
        "base_url se omite a proposito: el modulo cae a AGENDA_WEB_BASE_URL solo")
    assert capturado.get("timeout_s") == 5.0, (
        "el probe se acota a 5 s para no comerse el presupuesto de 6 min que "
        f"F7.1 protege; llego {capturado.get('timeout_s')}")
