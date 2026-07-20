"""Plan 198 F0 — Bitácora de applies de ambientes: flag + servicio JSONL + endpoint con drift.

Tests (TDD, por archivo — gotcha reload de config):
  - flag declarada bool default ON + curada.
  - endpoint 404 con ledger OFF y con environments OFF.
  - KPI-2: ALLOWLIST descarta claves extra (anti-secreto) + cap 200 paths con paths_truncated.
  - KPI-4: retención MAX_ROWS=500 + SORT DESC por applied_at (no orden de archivo).
  - KPI-3: drift True/False/None por comparación de fingerprints.
  - líneas corruptas no rompen la lectura.
  - filtros exactos por root y server_alias.

RECETA de ledger CONGELADA del 191 (services/ci_run_ledger.py), otro dominio/campos.
"""
from __future__ import annotations

import json

import pytest

import config
import runtime_paths


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _tmp_data_dir(tmp_path, monkeypatch):
    """Redirige el ledger a tmp_path (cero escritura en el data_dir real)."""
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture()
def app():
    from app import create_app
    _app = create_app()
    _app.config["TESTING"] = True
    return _app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture()
def _fake_env_context(monkeypatch):
    """Monkeypatch de _load_env_context y layout_fingerprint (estilo tests de environments):
    el endpoint no depende de disco/perfiles reales."""
    import api.devops as devops

    def _ctx(body):
        root = body.get("_root", "C:/amb")
        rel = body.get("_rel", ["a/b", "a/c"])
        return (root, rel, False, body.get("server_alias")), None

    monkeypatch.setattr(devops, "_load_env_context", _ctx)
    # current_fingerprint controlable por test.
    monkeypatch.setattr(devops, "layout_fingerprint", lambda root, rel: "CUR")
    return devops


# ---------------------------------------------------------------------------
# Flag
# ---------------------------------------------------------------------------

def test_flag_declarada_bool_default_on():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert "STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED" in by_key
    spec = by_key["STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED"]
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_flag_en_curated_defaults_on():
    from services.harness_flags import FLAG_REGISTRY, declared_default, default_is_known

    spec = {s.key: s for s in FLAG_REGISTRY}["STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED"]
    assert declared_default(spec) is True
    assert default_is_known(spec) is True


# ---------------------------------------------------------------------------
# Endpoint POST /api/devops/environments/applies — flags
# ---------------------------------------------------------------------------

def test_endpoint_404_ledger_off(client, monkeypatch, _tmp_data_dir, _fake_env_context):
    monkeypatch.setattr(config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED", False)
    resp = client.post("/api/devops/environments/applies", json={"project": "p"})
    assert resp.status_code == 404


def test_endpoint_404_environments_off(client, monkeypatch, _tmp_data_dir, _fake_env_context):
    monkeypatch.setattr(config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False)
    monkeypatch.setattr(config.config, "STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED", True)
    resp = client.post("/api/devops/environments/applies", json={"project": "p"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Servicio — ALLOWLIST + cap
# ---------------------------------------------------------------------------

def test_kpi2_allowlist_y_cap_paths(_tmp_data_dir):
    from services.env_apply_ledger import append_apply

    append_apply({
        "root": "C:/amb",
        "server_alias": None,
        "paths": [f"p/{i}" for i in range(250)],
        "fingerprint": "FP",
        "password": "supersecret",          # clave fuera de la ALLOWLIST
        "token": "ghp_xxxxxxxx",            # otra clave prohibida
    })
    text = (_tmp_data_dir / "env_applies.jsonl").read_text(encoding="utf-8")
    assert "password" not in text
    assert "supersecret" not in text
    assert "token" not in text
    row = json.loads(text.splitlines()[0])
    assert len(row["paths"]) == 200          # cap 200
    assert row["paths_truncated"] is True


def test_cap_no_trunca_si_cabe(_tmp_data_dir):
    from services.env_apply_ledger import append_apply, list_applies

    append_apply({"root": "C:/amb", "server_alias": None, "paths": ["a", "b"], "fingerprint": "FP"})
    rows = list_applies(root="C:/amb")
    assert rows[0]["paths_truncated"] is False
    assert rows[0]["paths"] == ["a", "b"]


# ---------------------------------------------------------------------------
# Servicio — retención + orden
# ---------------------------------------------------------------------------

def test_kpi4_retencion_y_orden(_tmp_data_dir):
    from services.env_apply_ledger import append_apply, list_applies, MAX_ROWS

    for i in range(MAX_ROWS + 1):
        append_apply({
            "root": "C:/amb",
            "server_alias": None,
            "paths": ["x"],
            "fingerprint": "FP",
            "applied_at": f"2024-01-01T00:00:{i % 60:02d}.{i:06d}+00:00",
        })
    lines = [l for l in (_tmp_data_dir / "env_applies.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == MAX_ROWS            # KPI-4: 501 → 500

    # SORT DESC por applied_at (no orden de archivo).
    from services.env_apply_ledger import append_apply as _aa
    (_tmp_data_dir / "env_applies.jsonl").unlink()
    _aa({"root": "R", "server_alias": None, "paths": [], "fingerprint": "a", "applied_at": "2021-01-01T00:00:00+00:00"})
    _aa({"root": "R", "server_alias": None, "paths": [], "fingerprint": "b", "applied_at": "2023-01-01T00:00:00+00:00"})
    _aa({"root": "R", "server_alias": None, "paths": [], "fingerprint": "c", "applied_at": "2022-01-01T00:00:00+00:00"})
    rows = list_applies(root="R")
    assert [r["fingerprint"] for r in rows] == ["b", "c", "a"]


def test_limit_clamp(_tmp_data_dir):
    from services.env_apply_ledger import append_apply, list_applies, MAX_ROWS

    append_apply({"root": "R", "server_alias": None, "paths": [], "fingerprint": "x"})
    assert len(list_applies(root="R", limit=0)) == 1          # 0 → 1
    assert len(list_applies(root="R", limit=-9)) == 1         # negativo → 1
    assert len(list_applies(root="R", limit=99999)) <= MAX_ROWS


# ---------------------------------------------------------------------------
# KPI-3 — drift por fingerprint (via endpoint)
# ---------------------------------------------------------------------------

def test_kpi3_drift_true_false_null(client, monkeypatch, _tmp_data_dir, _fake_env_context):
    from services.env_apply_ledger import append_apply

    monkeypatch.setattr(config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED", True)

    # (1) sin applies previos → drift None.
    resp = client.post("/api/devops/environments/applies", json={"project": "p", "_root": "C:/amb"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["layout_drift"] is None
    assert body["current_fingerprint"] == "CUR"
    assert body["last_applied_fingerprint"] is None

    # (2) último apply con MISMO fingerprint que el actual → drift False.
    append_apply({"root": "C:/amb", "server_alias": None, "paths": ["a"], "fingerprint": "CUR"})
    resp = client.post("/api/devops/environments/applies", json={"project": "p", "_root": "C:/amb"})
    body = resp.get_json()
    assert body["layout_drift"] is False
    assert body["last_applied_fingerprint"] == "CUR"

    # (3) último apply con fingerprint DISTINTO → drift True.
    append_apply({"root": "C:/amb", "server_alias": None, "paths": ["a"], "fingerprint": "OTRO"})
    resp = client.post("/api/devops/environments/applies", json={"project": "p", "_root": "C:/amb"})
    body = resp.get_json()
    assert body["layout_drift"] is True
    assert body["last_applied_fingerprint"] == "OTRO"


# ---------------------------------------------------------------------------
# Robustez + filtros
# ---------------------------------------------------------------------------

def test_lineas_corruptas_no_rompen(_tmp_data_dir):
    from services.env_apply_ledger import list_applies

    path = _tmp_data_dir / "env_applies.jsonl"
    path.write_text(
        "{ no es json valido\n"
        + json.dumps({"root": "R", "server_alias": None, "fingerprint": "ok",
                      "applied_at": "2024-01-01T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    rows = list_applies(root="R")
    assert len(rows) == 1
    assert rows[0]["fingerprint"] == "ok"


def test_filtro_root_y_server(_tmp_data_dir):
    from services.env_apply_ledger import append_apply, list_applies, last_fingerprint

    append_apply({"root": "R1", "server_alias": None, "paths": [], "fingerprint": "a"})
    append_apply({"root": "R2", "server_alias": None, "paths": [], "fingerprint": "b"})
    append_apply({"root": "R1", "server_alias": "srv", "paths": [], "fingerprint": "c"})

    # root filtra exacto; server_alias None = SIN filtro de server (recipe 191: None=no viene).
    assert {r["fingerprint"] for r in list_applies(root="R1")} == {"a", "c"}
    assert {r["fingerprint"] for r in list_applies(root="R2")} == {"b"}
    # server_alias provisto = filtro exacto adicional.
    assert {r["fingerprint"] for r in list_applies(root="R1", server_alias="srv")} == {"c"}

    # last_fingerprint SIEMPRE exacto en (root, server_alias) — None = local (para el drift).
    assert last_fingerprint("R1", None) == "a"
    assert last_fingerprint("R1", "srv") == "c"
    assert last_fingerprint("R2", "srv") is None
