"""Plan 157 F3 — Guardarraíles de datos personales y secretos (instrucción de la
organización). Los 5 requisitos (a-e) + el self-check de egreso fail-closed (ADICIÓN v2)
como invariantes con evidencia binaria.

Ver Stacky Agents/docs/157_PLAN_DB_COMPARE_CONFIG_IN_PLACE_WEBCONFIG_IMPORT_Y_PANEL_MIGRACION.md
"""
from __future__ import annotations

import json
import logging
import os
import socket
import urllib.request

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import api.db_compare as db_compare_mod
import runtime_paths
import services.dbcompare_config_import as cimport
import services.dbcompare_registry as reg
from services.dbcompare_config_import import parse_connection_string, parse_webconfig
from services.egress_policies import detect_classes

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


@pytest.fixture
def app_on(tmp_path, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED", True, raising=False)
    fake = _FakeKeyring()
    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(reg, "keyring", fake)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    cimport._clear_cache()
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app._tmp = tmp_path
    yield app
    cimport._clear_cache()


def _c(app):
    return app.test_client()


# ── (a) No loguear en claro ─────────────────────────────────────────────────
def test_a_import_no_loguea_password_en_claro(app_on, caplog):
    c = _c(app_on)
    with caplog.at_level(logging.DEBUG):
        body = c.post("/api/db-compare/environments/import-config", json={"content": _CS}).get_json()
        c.post(
            "/api/db-compare/environments/import-config/confirm",
            json={"import_id": body["import_id"], "index": 0, "alias": "test-a"},
        )
    joined = "\n".join(f"{r.getMessage()} {r.args}" for r in caplog.records)
    assert _SECRET not in joined


# ── (b) Enmascarar: masked_raw sin secreto (reuso F1) ───────────────────────
def test_b_masked_raw_sin_secreto():
    pc, pw = parse_connection_string(_CS)
    assert pw == _SECRET
    assert _SECRET not in pc.masked_raw
    assert "Password=****" in pc.masked_raw


# ── (c) Sin texto plano en disco / respuesta ────────────────────────────────
def test_c_environments_json_sin_password(app_on):
    c = _c(app_on)
    body = c.post("/api/db-compare/environments/import-config", json={"content": _CS}).get_json()
    c.post(
        "/api/db-compare/environments/import-config/confirm",
        json={"import_id": body["import_id"], "index": 0, "alias": "PACIFICO-DEV"},
    )
    env_json = app_on._tmp / "db_compare" / "environments.json"
    assert env_json.exists()
    text = env_json.read_text(encoding="utf-8")
    assert _SECRET not in text
    assert '"password"' not in text.lower()


def test_c_respuesta_confirm_sin_password(app_on):
    c = _c(app_on)
    body = c.post("/api/db-compare/environments/import-config", json={"content": _CS}).get_json()
    r = c.post(
        "/api/db-compare/environments/import-config/confirm",
        json={"import_id": body["import_id"], "index": 0, "alias": "test-c2"},
    )
    assert _SECRET not in json.dumps(r.get_json())


# ── (e) Parseo local sin egreso ─────────────────────────────────────────────
def test_e_parser_no_hace_red(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("el parser NO debe abrir la red")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    xml = (
        "<configuration><connectionStrings>"
        + "".join(
            f'<add name="n{i}" providerName="System.Data.SqlClient" '
            f'connectionString="Server=s{i},1433;Database=RS;User ID=u;Password=Secr3t{i:03d};" />'
            for i in range(50)
        )
        + "</connectionStrings></configuration>"
    )
    conns = parse_webconfig(xml)
    assert len(conns) == 50  # sin excepción ⇒ no se invocó ninguna primitiva de red


def test_e_detector_egreso_marca_connstring():
    # Gotcha C5 v2: el detector exige \S{4,} tras password= ⇒ password de ≥4 chars.
    assert "secrets" in detect_classes("Server=x;Database=y;User ID=z;Password=Secr3t;")


# ── (ADICIÓN v2) Self-check de egreso fail-closed en la respuesta ───────────
def test_f_import_response_pasa_selfcheck(app_on):
    # content con password REAL: el body de import y confirm pasa el self-check
    # (previews enmascarados ⇒ no matchea `secrets`) ⇒ 200, no 500.
    c = _c(app_on)
    r = c.post("/api/db-compare/environments/import-config", json={"content": _CS})
    assert r.status_code == 200
    body = r.get_json()
    r2 = c.post(
        "/api/db-compare/environments/import-config/confirm",
        json={"import_id": body["import_id"], "index": 0, "alias": "test-f1"},
    )
    assert r2.status_code == 200


def test_f_selfcheck_aborta_si_secreto_colara(app_on, monkeypatch):
    # Si un bug dejara colar un secreto en el preview, el endpoint corta con 500
    # (fail-closed) y la respuesta NO contiene el secreto.
    leaked = "Password=Secr3tLeak99"

    def _leaky_previews(conns):
        return [{"leaked": leaked, "index": 0}]

    monkeypatch.setattr(db_compare_mod, "_build_previews", _leaky_previews)
    c = _c(app_on)
    r = c.post("/api/db-compare/environments/import-config", json={"content": _CS})
    assert r.status_code == 500
    assert "Secr3tLeak99" not in json.dumps(r.get_json())
