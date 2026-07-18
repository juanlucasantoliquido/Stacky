"""Plan 157 F2 — Endpoints de import local + confirmación a keyring.

Ver Stacky Agents/docs/157_PLAN_DB_COMPARE_CONFIG_IN_PLACE_WEBCONFIG_IMPORT_Y_PANEL_MIGRACION.md
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import runtime_paths
import services.dbcompare_config_import as cimport
import services.dbcompare_registry as reg

_CS = "Server=srv,1433;Database=RS;User ID=rs;Password=Secr3t123;"
_SECRET = "Secr3t123"


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, svc, key, val):
        self.store[(svc, key)] = val

    def get_password(self, svc, key):
        return self.store.get((svc, key))

    def delete_password(self, svc, key):
        self.store.pop((svc, key), None)


def _mk_app(tmp_path, monkeypatch, *, master=True, import_on=True):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", master, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED", import_on, raising=False)
    fake = _FakeKeyring()
    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(reg, "keyring", fake)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)  # tmp_path bajo allowlist
    cimport._clear_cache()
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app, fake


@pytest.fixture
def app_on(tmp_path, monkeypatch):
    app, fake = _mk_app(tmp_path, monkeypatch)
    app._fake_keyring = fake
    yield app
    cimport._clear_cache()


@pytest.fixture
def app_import_off(tmp_path, monkeypatch):
    app, _ = _mk_app(tmp_path, monkeypatch, master=True, import_on=False)
    yield app
    cimport._clear_cache()


def _c(app):
    return app.test_client()


def test_import_403_si_flag_off(app_import_off):
    c = _c(app_import_off)
    r = c.post("/api/db-compare/environments/import-config", json={"content": _CS})
    assert r.status_code == 403
    r = c.post("/api/db-compare/environments/import-config/confirm", json={"import_id": "x", "index": 0, "alias": "a"})
    assert r.status_code == 403


def test_import_content_devuelve_previews_sin_password(app_on):
    c = _c(app_on)
    r = c.post("/api/db-compare/environments/import-config", json={"content": _CS})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["ok"] is True
    assert "import_id" in body
    conns = body["connections"]
    assert len(conns) == 1
    preview = conns[0]
    assert preview["has_password"] is True
    assert preview["engine"] == "sqlserver"
    assert preview["index"] == 0
    assert "password" not in preview
    assert "masked_raw" not in preview
    # Ningún value de la respuesta contiene la password en claro.
    assert _SECRET not in json.dumps(body)


def test_import_webconfig_multiples_previews(app_on):
    xml = (
        "<configuration><connectionStrings>"
        '<add name="Dev" providerName="System.Data.SqlClient" '
        'connectionString="Server=devsrv,1433;Database=RS;User ID=u;Password=Secr3t123;" />'
        '<add name="Test" providerName="System.Data.SqlClient" '
        'connectionString="Server=testsrv,1433;Database=RS;User ID=u2;Password=Other999;" />'
        "</connectionStrings></configuration>"
    )
    c = _c(app_on)
    r = c.post("/api/db-compare/environments/import-config", json={"content": xml})
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["connections"]) == 2
    assert _SECRET not in json.dumps(body)
    assert "Other999" not in json.dumps(body)


def test_import_path_inexistente_404(app_on, tmp_path):
    c = _c(app_on)
    r = c.post("/api/db-compare/environments/import-config", json={"path": str(tmp_path / "nope.xml")})
    assert r.status_code == 404


def test_import_path_directorio_400(app_on, tmp_path):
    c = _c(app_on)
    r = c.post("/api/db-compare/environments/import-config", json={"path": str(tmp_path)})
    assert r.status_code == 400


def test_import_extension_no_permitida_415(app_on, tmp_path):
    bad = tmp_path / "foo.txt"
    bad.write_text(_CS, encoding="utf-8")
    c = _c(app_on)
    r = c.post("/api/db-compare/environments/import-config", json={"path": str(bad)})
    assert r.status_code == 415


def test_import_oversize_413(app_on, tmp_path):
    big = tmp_path / "big.xml"
    big.write_text("<x>" + ("a" * 1_000_050) + "</x>", encoding="utf-8")
    c = _c(app_on)
    r = c.post("/api/db-compare/environments/import-config", json={"path": str(big)})
    assert r.status_code == 413


def test_import_path_fuera_de_allowlist_403(app_on, tmp_path):
    outside = tmp_path.parent / "fuera_allowlist_157.xml"
    c = _c(app_on)
    r = c.post("/api/db-compare/environments/import-config", json={"path": str(outside)})
    assert r.status_code == 403
    assert r.get_json()["error"] == "path_fuera_de_allowlist"


def test_confirm_crea_ambiente_y_setea_keyring(app_on):
    c = _c(app_on)
    r = c.post("/api/db-compare/environments/import-config", json={"content": _CS})
    body = r.get_json()
    import_id = body["import_id"]
    r = c.post(
        "/api/db-compare/environments/import-config/confirm",
        json={"import_id": import_id, "index": 0, "alias": "PACIFICO-DEV"},
    )
    assert r.status_code == 200, r.get_json()
    conf = r.get_json()
    assert conf["ok"] is True
    assert conf["alias"] == "PACIFICO-DEV"
    assert _SECRET not in json.dumps(conf)

    # El ambiente quedó registrado.
    envs = c.get("/api/db-compare/environments").get_json()["environments"]
    aliases = {e["alias"] for e in envs}
    assert "PACIFICO-DEV" in aliases
    # La password fue a keyring (nunca a la respuesta ni al JSON en disco).
    assert app_on._fake_keyring.get_password("stacky-dbcompare", "PACIFICO-DEV") == _SECRET


def test_confirm_import_id_inexistente_404(app_on):
    c = _c(app_on)
    r = c.post(
        "/api/db-compare/environments/import-config/confirm",
        json={"import_id": "no-existe", "index": 0, "alias": "X"},
    )
    assert r.status_code == 404


def test_confirm_indice_consumido_una_sola_vez(app_on):
    c = _c(app_on)
    body = c.post("/api/db-compare/environments/import-config", json={"content": _CS}).get_json()
    import_id = body["import_id"]
    r1 = c.post(
        "/api/db-compare/environments/import-config/confirm",
        json={"import_id": import_id, "index": 0, "alias": "test-a"},
    )
    assert r1.status_code == 200
    r2 = c.post(
        "/api/db-compare/environments/import-config/confirm",
        json={"import_id": import_id, "index": 0, "alias": "test-b"},
    )
    assert r2.status_code == 404  # tombstone: no se puede reconfirmar el mismo índice


def test_logs_no_contienen_password(app_on, caplog):
    import logging

    c = _c(app_on)
    with caplog.at_level(logging.DEBUG):
        body = c.post("/api/db-compare/environments/import-config", json={"content": _CS}).get_json()
        c.post(
            "/api/db-compare/environments/import-config/confirm",
            json={"import_id": body["import_id"], "index": 0, "alias": "test-logs"},
        )
    joined = "\n".join(f"{r.getMessage()} {r.args}" for r in caplog.records)
    assert _SECRET not in joined
