"""Plan 262 F2.4 — recovery_config: el lector unico de la config de recuperacion.

15 casos. Casos borde con decision escrita: no numerico -> default; fuera de
bounds -> clampeo; csv sucio -> limpio; base url sin barra -> normalizada.
NUNCA levanta: una ValueError aca terminaria rotulada PIPELINE_CRASH.
"""
from __future__ import annotations

import json

import pytest

import recovery_config as rc

_LAS_9 = (
    "STACKY_QA_UAT_HOT_RECOVERY_ENABLED",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE",
    "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S",
    "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S",
    "STACKY_QA_UAT_ROUTE_ALLOWLIST",
    "STACKY_QA_UAT_SAFE_ROUTE",
    "AGENDA_WEB_BASE_URL",
    "QA_NAV_RETRIES",
)


@pytest.fixture(autouse=True)
def _limpiar_env(monkeypatch):
    """Cada caso arranca sin ninguna de las 9 en el entorno."""
    for k in _LAS_9:
        monkeypatch.delenv(k, raising=False)


def test_defaults_completos():
    faltantes = [k for k in _LAS_9 if k not in rc.DEFAULTS]
    assert faltantes == [], f"keys ausentes de recovery_config.DEFAULTS: {faltantes}"


def test_bool_true_por_default():
    assert rc.hot_recovery_enabled() is True


def test_bool_off_respetado(monkeypatch):
    """Un solo caso con las 3 formas de apagar (el plan cuenta 15 casos, no 17)."""
    for apagado in ("false", "0", "no"):
        monkeypatch.setenv("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", apagado)
        assert rc.hot_recovery_enabled() is False, f"{apagado!r} deberia apagar la flag"


def test_int_no_numerico_cae_al_default(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_RECOVERY_MAX_PER_RUN", "abc")
    assert rc.recovery_max_per_run() == 6


def test_int_fuera_de_bounds_se_clampea(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_RECOVERY_MAX_PER_RUN", "999")
    assert rc.recovery_max_per_run() == 50


def test_float_timeout_negativo_se_clampea(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S", "-3")
    assert rc.health_probe_timeout_s() == 1.0


def test_confirm_s_cero_es_valido(monkeypatch):
    """Cero es una eleccion legitima: confirmar sin pausa, con 2 muestras igual."""
    monkeypatch.setenv("STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S", "0")
    assert rc.health_probe_confirm_s() == 0.0


def test_confirm_s_fuera_de_bounds_se_clampea(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S", "99")
    assert rc.health_probe_confirm_s() == 15.0


def test_csv_limpia_espacios_y_vacios(monkeypatch):
    monkeypatch.setenv(
        "STACKY_QA_UAT_ROUTE_ALLOWLIST", " FrmLogin.aspx , ,FrmBusqueda.aspx "
    )
    assert rc.route_allowlist_raw() == ["FrmLogin.aspx", "FrmBusqueda.aspx"]


def test_csv_vacio_da_lista_vacia():
    assert rc.route_allowlist_raw() == []


def test_base_url_normaliza_barra_final(monkeypatch):
    """Igual que environment_preflight.py:77 — raw.rstrip('/') + '/'."""
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://x:8080/AgendaWeb")
    assert rc.base_url() == "http://x:8080/AgendaWeb/"


def test_safe_route_es_string_no_lista(monkeypatch):
    """v2/C5: type='str'. Falla si alguien la implementa como csv y devuelve list."""
    monkeypatch.setenv("STACKY_QA_UAT_SAFE_ROUTE", "FrmBusqueda.aspx")
    valor = rc.safe_route_raw()
    assert isinstance(valor, str), f"safe_route_raw() devolvio {type(valor).__name__}"
    assert valor == "FrmBusqueda.aspx"


def test_nav_retries_default_es_3():
    """v2/C9 — el efectivo de hoy es 3. Un 1 aca seria una regresion silenciosa."""
    assert rc.nav_retries() == 3


def test_validate_detecta_safe_route_fuera_de_allowlist(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_ROUTE_ALLOWLIST", "FrmLogin.aspx,FrmBusqueda.aspx")
    monkeypatch.setenv("STACKY_QA_UAT_SAFE_ROUTE", "FrmFueraDeLista.aspx")
    problemas = rc.validate_recovery_config()
    assert problemas, "una ruta segura fuera de la allowlist es un bucle garantizado"
    assert any("FrmFueraDeLista.aspx" in p for p in problemas), problemas


def test_snapshot_no_expone_credenciales(monkeypatch):
    monkeypatch.setenv("AGENDA_WEB_USER", "usuario_secreto")
    monkeypatch.setenv("AGENDA_WEB_PASS", "clave_secreta")
    texto = json.dumps(rc.snapshot())
    for prohibido in ("AGENDA_WEB_USER", "AGENDA_WEB_PASS",
                      "usuario_secreto", "clave_secreta"):
        assert prohibido not in texto, f"snapshot() expone {prohibido}"
