"""test_plan241_qa_uat.py — Plan 241 F8 (cierra también F8 del Plan 240).

Cubre: las 5 flags del agente QA UAT E2E en los 5 lugares obligatorios, el endpoint
read-only `runtime-doctor`, la exportación de flags al entorno del pipeline y las
huellas de regresión sembradas.
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_REPO_ROOT = ROOT.parent.parent

_ON_FLAGS = (
    "STACKY_QA_UAT_ADO_BRIDGE_ENABLED",
    "STACKY_QA_UAT_FUNCTIONAL_VERDICT_ENABLED",
    "STACKY_QA_UAT_STRICT_DISCRIMINATION_ENABLED",
    "STACKY_QA_UAT_EPIC_ROLLUP_ENABLED",
)
_OFF_FLAG = "STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED"
_ALL_FLAGS = _ON_FLAGS + (_OFF_FLAG,)


@pytest.fixture(scope="module")
def app():
    from app import create_app
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


# ── Flags: los 5 lugares obligatorios ────────────────────────────────────────

def test_flags_registradas():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    keys = {s.key for s in FLAG_REGISTRY}
    for k in _ALL_FLAGS:
        assert k in keys, f"{k} falta en FLAG_REGISTRY"
        assert k in _CATEGORY_KEYS["calidad_verificacion"], f"{k} sin categoría"


def test_defaults_de_config():
    from config import Config
    cfg = Config()
    for k in _ON_FLAGS:
        assert getattr(cfg, k) is True, k
    # EXCEPCIÓN DURA #3: prerequisito no garantizado (IIS Express + apphost config).
    assert getattr(cfg, _OFF_FLAG) is False


def test_solo_las_on_en_curated():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    for k in _ON_FLAGS:
        assert k in _CURATED_DEFAULTS_ON, k
    assert _OFF_FLAG not in _CURATED_DEFAULTS_ON


def test_sin_aristas_requires():
    """Las 5 flags son independientes entre sí: ninguna vive dentro del branch de
    otra, así que NO corresponde declarar `requires`."""
    from services.harness_flags import FLAG_REGISTRY
    specs = {s.key: s for s in FLAG_REGISTRY}
    for k in _ALL_FLAGS:
        assert specs[k].requires is None, f"{k} no debería declarar requires"


def test_flags_se_exportan_al_entorno(monkeypatch):
    """El toggle de la UI tiene que llegar al tool, que lee por os.environ."""
    import config as config_mod
    from api.qa_uat import _export_qa_uat_flags

    monkeypatch.setattr(config_mod.config, "STACKY_QA_UAT_ADO_BRIDGE_ENABLED", True,
                        raising=False)
    monkeypatch.setattr(config_mod.config, _OFF_FLAG, False, raising=False)
    for k in _ALL_FLAGS:
        monkeypatch.delenv(k, raising=False)

    exported = _export_qa_uat_flags()
    assert exported["STACKY_QA_UAT_ADO_BRIDGE_ENABLED"] == "true"
    assert exported[_OFF_FLAG] == "false"
    assert os.environ["STACKY_QA_UAT_ADO_BRIDGE_ENABLED"] == "true"
    assert os.environ[_OFF_FLAG] == "false"


# ── Endpoint runtime-doctor ──────────────────────────────────────────────────

def test_doctor_endpoint_200(client):
    r = client.get("/api/qa-uat/runtime-doctor")
    assert r.status_code == 200
    body = r.get_json()
    for key in ("ok", "browser", "agenda", "ado_bridge", "version_drift"):
        assert key in body, key


def test_doctor_degrada_sin_guard(client, monkeypatch):
    """Un import roto responde 200 con browser.code GUARD_UNAVAILABLE, nunca 5xx."""
    import builtins
    real_import = builtins.__import__

    def _fake_import(name, *a, **kw):
        if name == "browser_runtime_guard":
            raise ImportError("guard roto a proposito")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    r = client.get("/api/qa-uat/runtime-doctor")
    assert r.status_code == 200
    assert r.get_json()["browser"]["code"] == "GUARD_UNAVAILABLE"


# ── Huellas de regresión ─────────────────────────────────────────────────────

def test_huellas_sembradas():
    p = _REPO_ROOT / "Stacky Agents" / "docs" / "sistema" / "error_fingerprints.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    ids = {f.get("id") for f in data.get("fingerprints", [])}
    for fid in ("qa_uat_login_glob_false_negative", "qa_uat_nav_session_lost",
                "qa_uat_app_error_page"):
        assert fid in ids, fid


def test_ratchet_registra_este_archivo():
    """Un test_*.py nuevo del backend debe estar en HARNESS_TEST_FILES (.sh Y .ps1)."""
    for script in ("scripts/run_harness_tests.sh", "scripts/run_harness_tests.ps1"):
        txt = (ROOT / script).read_text(encoding="utf-8")
        assert "test_plan241_qa_uat.py" in txt, script


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
