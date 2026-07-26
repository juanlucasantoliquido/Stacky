"""Plan 210 F3 — Endpoint disparador de la verificación de build."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import api.dev_build as api_dev_build  # noqa: E402
from services import dev_build_verify as dbv  # noqa: E402

_RUTA = "/api/tickets/by-ado/424242/dev/build-verify"


@pytest.fixture(scope="module")
def client():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DEV_BUILD_VERIFY_ENABLED", True, raising=False)


def test_verify_off_returns_404(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DEV_BUILD_VERIFY_ENABLED", False, raising=False)

    assert client.post(_RUTA).status_code == 404


def test_verify_returns_verdict_200(client, monkeypatch):
    fake = dbv.BuildVerdict(ok=True, gate_ok=True, entry_kind="sln", reason="ok",
                            solution="App.sln", returncode=0, execution_id=9)
    monkeypatch.setattr(api_dev_build.dev_build_verify, "verify_build",
                        lambda **kw: fake, raising=True)

    r = client.post(_RUTA)

    assert r.status_code == 200
    verdict = r.get_json()["verdict"]
    assert verdict["gate_ok"] is True
    assert verdict["reason"] == "ok"
    assert verdict["execution_id"] == 9


def test_verify_unknown_ado_still_200_blocking(client, monkeypatch):
    """Un ado_id sin ticket no es un 500: es un veredicto bloqueante."""
    recibidos: list = []

    def _verify(**kw):
        recibidos.append(kw)
        return dbv._not_verified("workspace_missing")

    monkeypatch.setattr(api_dev_build.dev_build_verify, "verify_build", _verify,
                        raising=True)

    r = client.post(_RUTA)

    assert r.status_code == 200
    assert r.get_json()["verdict"]["gate_ok"] is False
    assert recibidos[0]["project_name"] is None


def test_endpoint_pasa_la_ejecucion_actual(client, monkeypatch):
    recibidos: list = []
    monkeypatch.setattr(api_dev_build.dev_build_verify, "latest_execution_id_for_ado",
                        lambda a: 123, raising=True)
    monkeypatch.setattr(api_dev_build.dev_build_verify, "workspace_root_for_ado",
                        lambda a: "C:\\ws", raising=True)
    monkeypatch.setattr(api_dev_build.dev_build_verify, "verify_build",
                        lambda **kw: recibidos.append(kw) or dbv._not_verified("not_verified"),
                        raising=True)

    client.post(_RUTA)

    assert recibidos[0]["execution_id"] == 123, "el veredicto se liga a la corrida actual"
    assert recibidos[0]["ado_id"] == 424242


def test_blueprint_registrado():
    fuente = (ROOT / "api" / "__init__.py").read_text(encoding="utf-8")

    assert fuente.count("dev_build_bp") == 2, "import + register"
