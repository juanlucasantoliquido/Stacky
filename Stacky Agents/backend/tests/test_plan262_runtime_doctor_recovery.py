"""Plan 262 F10.3 — el runtime-doctor del 240 F8 se EXTIENDE, no se duplica.

7 casos. test_las_claves_previas_del_doctor_siguen es la guarda de no-regresion:
la seccion nueva es aditiva y ninguna clave existente cambia de nombre ni tipo.
test_health_se_reporta_aunque_la_app_este_caida existe porque un doctor que
devuelve 500 cuando el entorno esta roto es un doctor inutil.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

# Claves top-level que el doctor ya devolvia antes de este plan.
_CLAVES_PREVIAS = {"ok", "browser", "agenda", "ado_bridge", "version_drift"}

_LAS_9 = {
    "STACKY_QA_UAT_HOT_RECOVERY_ENABLED",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE",
    "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S",
    "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S",
    "STACKY_QA_UAT_ROUTE_ALLOWLIST",
    "STACKY_QA_UAT_SAFE_ROUTE",
    "AGENDA_WEB_BASE_URL",
    "QA_NAV_RETRIES",
}


@pytest.fixture()
def doctor():
    """Llama al endpoint real con un cliente Flask de prueba."""
    from app import create_app
    app = create_app()
    with app.test_client() as client:
        yield client


def _payload(client):
    r = client.get("/api/qa-uat/runtime-doctor")
    assert r.status_code == 200, f"el doctor devolvio {r.status_code}, debe ser 200"
    return r.get_json()


def test_doctor_tiene_seccion_hot_recovery(doctor):
    datos = _payload(doctor)
    assert "hot_recovery" in datos
    assert isinstance(datos["hot_recovery"], dict)


def test_las_claves_previas_del_doctor_siguen(doctor):
    """GATE DE NO-REGRESION: el set de claves de hoy debe seguir siendo subconjunto."""
    datos = _payload(doctor)
    faltantes = sorted(_CLAVES_PREVIAS - set(datos))
    assert faltantes == [], f"la seccion nueva rompio claves existentes: {faltantes}"


def test_config_expuesta_no_trae_password(doctor):
    import json
    datos = _payload(doctor)
    texto = json.dumps(datos["hot_recovery"])
    for prohibido in ("AGENDA_WEB_PASS", "AGENDA_WEB_USER"):
        assert prohibido not in texto, f"el doctor expone {prohibido}"


def test_allowlist_declara_su_source(doctor):
    datos = _payload(doctor)
    allowlist = datos["hot_recovery"]["allowlist"]
    assert allowlist.get("source") in ("derived", "configured", "unavailable")
    assert "count" in allowlist


def test_health_se_reporta_aunque_la_app_este_caida(doctor):
    """Probe muerto => 200 con alive:false, NUNCA un 500."""
    import agenda_health
    from agenda_health import HealthProbe
    muerta = HealthProbe(False, None, "http://x/", 5000, "URLError: refused",
                         "http_probe", 1)
    with patch.object(agenda_health, "probe_agenda", return_value=muerta):
        datos = _payload(doctor)
    assert datos["hot_recovery"]["health"]["alive"] is False


def test_flags_exported_lista_las_9(doctor):
    datos = _payload(doctor)
    exportadas = {f["key"] for f in datos["hot_recovery"]["flags_exported"]}
    faltantes = sorted(_LAS_9 - exportadas)
    assert faltantes == [], f"claves del plan 262 que el doctor no reporta: {faltantes}"


def test_health_expone_samples_y_source(doctor):
    """v2/F1.5 — sin esto el operador no puede distinguir un flap de una caida."""
    datos = _payload(doctor)
    health = datos["hot_recovery"]["health"]
    assert "samples" in health
    assert "source" in health
