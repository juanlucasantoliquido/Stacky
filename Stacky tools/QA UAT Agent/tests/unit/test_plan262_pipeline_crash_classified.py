"""Plan 262 F8 — fin del catch-all mudo: clasificar ANTES de rotular.

12 casos. Los dos primeros SON el sintoma que reporto el operador: hoy los dos dan
OPS/PIPELINE_CRASH, y por eso una ruta mal construida se lee como "AgendaWeb no
esta disponible". test_traceback_se_conserva impide "arreglarlo" tirando el
traceback que el plan 241 F6 agrego a proposito.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import qa_uat_pipeline as qp
from agenda_health import HealthProbe

_BASE = "http://localhost:35017/AgendaWeb/"


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", _BASE)
    for k in ("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "STACKY_QA_UAT_ROUTE_ALLOWLIST",
              "STACKY_QA_UAT_SAFE_ROUTE"):
        monkeypatch.delenv(k, raising=False)


def _viva():
    return HealthProbe(True, 200, _BASE, 5, "", "http_probe_confirmed", 2)


def _muerta():
    return HealthProbe(False, None, _BASE, 5000, "URLError: refused",
                       "http_probe_confirmed", 2)


def test_crash_con_app_caida_da_env_app_not_running():
    out = qp.classify_pipeline_crash(RuntimeError("boom"), route_used="FrmBusqueda.aspx",
                                     probe=_muerta())
    assert out["category"] == "ENV"
    assert out["reason"] == "APP_NOT_RUNNING"


def test_crash_con_app_viva_y_ruta_mala_da_nav_route_invalid():
    """EL SINTOMA DEL OPERADOR. Hoy esto sale OPS/PIPELINE_CRASH."""
    out = qp.classify_pipeline_crash(RuntimeError("boom"),
                                     route_used="http://otrohost:9999/Rara.aspx",
                                     probe=_viva())
    assert out["category"] == "NAV"
    assert out["reason"] == "ROUTE_INVALID"


def test_crash_con_app_viva_y_ruta_legal_conserva_ops():
    """Sin senal de navegacion, un crash generico sigue siendo OPS: no se inventa
    una causa."""
    out = qp.classify_pipeline_crash(RuntimeError("boom"), route_used="FrmBusqueda.aspx",
                                     probe=_viva())
    assert out["category"] == "OPS"
    assert out["reason"] == "PIPELINE_CRASH"


def test_verdict_sigue_siendo_blocked_en_los_3_casos():
    """GATE DE INV-1. Un crash no previsto no es un FAIL funcional ni un PASS."""
    casos = [
        dict(route_used="FrmBusqueda.aspx", probe=_muerta()),
        dict(route_used="http://otrohost:9999/Rara.aspx", probe=_viva()),
        dict(route_used="FrmBusqueda.aspx", probe=_viva()),
    ]
    for c in casos:
        out = qp.classify_pipeline_crash(RuntimeError("boom"), **c)
        assert out["verdict"] == "BLOCKED", c


def test_traceback_se_conserva():
    """GATE DEL 241 F6: un crash que esconde su ubicacion es un diagnostico mentiroso."""
    tb = 'File "qa_uat_pipeline.py", line 42, in run\n    raise RuntimeError("boom")'
    out = qp.classify_pipeline_crash(RuntimeError("boom"), route_used="a.aspx",
                                     probe=_viva(), traceback_text=tb)
    assert out["traceback"]
    assert "qa_uat_pipeline.py" in out["traceback"]


def test_traceback_se_recorta_a_2000():
    out = qp.classify_pipeline_crash(RuntimeError("boom"), route_used="a.aspx",
                                     probe=_viva(), traceback_text="x" * 5000)
    assert len(out["traceback"]) == 2000


def test_clasificador_roto_cae_al_rotulo_historico():
    """Un clasificador que rompe NO puede empeorar el diagnostico (INV-8)."""
    import recovery_classifier
    with patch.object(recovery_classifier, "classify_recovery",
                      side_effect=RuntimeError("clasificador roto")):
        out = qp.classify_pipeline_crash(RuntimeError("boom"), route_used="a.aspx",
                                         probe=_viva())
    assert out["category"] == "OPS"
    assert out["reason"] == "PIPELINE_CRASH"


def test_flag_off_es_byte_identico(monkeypatch):
    """GATE DE INV-8: con la flag apagada, el rotulo historico exacto."""
    monkeypatch.setenv("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "false")
    out = qp.classify_pipeline_crash(RuntimeError("boom"),
                                     route_used="http://otrohost:9999/Rara.aspx",
                                     probe=_muerta())
    assert out["category"] == "OPS"
    assert out["reason"] == "PIPELINE_CRASH"
    assert out["recovery_class"] is None
    assert out["recovery_evidence"] == ""
    assert out["app_alive"] is None


def test_route_used_llega_al_resultado():
    out = qp.classify_pipeline_crash(RuntimeError("boom"), route_used="FrmRota.aspx",
                                     probe=_viva())
    assert out["route_used"] == "FrmRota.aspx"


def test_app_alive_es_none_sin_clasificacion(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "false")
    out = qp.classify_pipeline_crash(RuntimeError("boom"), route_used="a.aspx",
                                     probe=_viva())
    assert out["app_alive"] is None


def test_last_route_used_lee_el_jsonl(tmp_path):
    evidencia = tmp_path / "evidence" / "123" / "run1"
    evidencia.mkdir(parents=True)
    jsonl = evidencia / "execution.jsonl"
    jsonl.write_text(
        json.dumps({"event": "nav", "data": {"url_before": "http://x/A.aspx"}}) + "\n" +
        json.dumps({"event": "nav", "data": {"url_after": "http://x/B.aspx"}}) + "\n",
        encoding="utf-8",
    )
    assert qp._last_route_used(tmp_path / "evidence") == "http://x/B.aspx"


def test_last_route_used_no_lanza_sin_archivos(tmp_path):
    assert qp._last_route_used(tmp_path / "no_existe") == ""
