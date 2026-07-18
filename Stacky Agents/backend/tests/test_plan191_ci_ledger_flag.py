"""Plan 191 F0 — Bitácora durable de corridas CI: flag + servicio JSONL + GET /api/ci/runs.

Tests (TDD, por archivo — gotcha reload de config):
  - flag declarada bool default ON + requires edge.
  - flag curada (default_is_known True).
  - endpoint 404 con flag OFF; 200 vacío con flag ON.
  - KPI-2: orden descendente por triggered_at (SORT, no orden de archivo) + limit.
  - C5: limit fuera de rango clampa a [1, MAX_ROWS].
  - KPI-3: retención MAX_ROWS=500.
  - allowlist ENTRY_FIELDS descarta claves fuera del contrato (anti-secreto).
  - líneas corruptas no rompen la lectura.
  - la ruta /runs no cae como /<project>/pipeline/... (congelamiento C1).
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


# ---------------------------------------------------------------------------
# Flag
# ---------------------------------------------------------------------------

def test_flag_declarada_bool_default_on():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert "STACKY_CI_RUN_LEDGER_ENABLED" in by_key
    spec = by_key["STACKY_CI_RUN_LEDGER_ENABLED"]
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == "STACKY_PIPELINE_TRIGGER_ENABLED"


def test_flag_en_curated_defaults_on():
    from services.harness_flags import FLAG_REGISTRY, declared_default, default_is_known

    spec = {s.key: s for s in FLAG_REGISTRY}["STACKY_CI_RUN_LEDGER_ENABLED"]
    assert declared_default(spec) is True
    assert default_is_known(spec) is True


# ---------------------------------------------------------------------------
# Endpoint GET /api/ci/runs
# ---------------------------------------------------------------------------

def test_endpoint_404_flag_off(client, monkeypatch, _tmp_data_dir):
    monkeypatch.setattr(config.config, "STACKY_CI_RUN_LEDGER_ENABLED", False)
    resp = client.get("/api/ci/runs")
    assert resp.status_code == 404


def test_endpoint_200_vacio_flag_on(client, monkeypatch, _tmp_data_dir):
    monkeypatch.setattr(config.config, "STACKY_CI_RUN_LEDGER_ENABLED", True)
    resp = client.get("/api/ci/runs")
    assert resp.status_code == 200
    assert resp.get_json() == {"runs": []}


def test_kpi2_orden_y_limit(client, monkeypatch, _tmp_data_dir):
    from services.ci_run_ledger import append_run

    # Sembradas EN DESORDEN de archivo respecto a triggered_at.
    append_run({"pipeline_id": "a", "triggered_at": "2021-01-01T00:00:00+00:00"})
    append_run({"pipeline_id": "b", "triggered_at": "2023-01-01T00:00:00+00:00"})
    append_run({"pipeline_id": "c", "triggered_at": "2022-01-01T00:00:00+00:00"})

    monkeypatch.setattr(config.config, "STACKY_CI_RUN_LEDGER_ENABLED", True)
    resp = client.get("/api/ci/runs")
    assert resp.status_code == 200
    runs = resp.get_json()["runs"]
    # SORT descendente por triggered_at, NO orden de archivo (C2).
    assert [r["pipeline_id"] for r in runs] == ["b", "c", "a"]

    resp2 = client.get("/api/ci/runs?limit=2")
    runs2 = resp2.get_json()["runs"]
    assert [r["pipeline_id"] for r in runs2] == ["b", "c"]


def test_limit_fuera_de_rango_clampa(_tmp_data_dir):
    from services.ci_run_ledger import append_run, list_runs, MAX_ROWS

    append_run({"pipeline_id": "solo", "triggered_at": "2024-01-01T00:00:00+00:00"})
    assert len(list_runs(limit=0)) == 1        # 0 → clamp a 1
    assert len(list_runs(limit=-5)) == 1       # negativo → clamp a 1
    assert len(list_runs(limit=99999)) <= MAX_ROWS  # tope superior


def test_endpoint_limit_invalido_400(client, monkeypatch, _tmp_data_dir):
    monkeypatch.setattr(config.config, "STACKY_CI_RUN_LEDGER_ENABLED", True)
    resp = client.get("/api/ci/runs?limit=abc")
    assert resp.status_code == 400


def test_kpi3_retencion_500(_tmp_data_dir):
    from services.ci_run_ledger import append_run, MAX_ROWS

    for i in range(MAX_ROWS + 1):
        append_run({
            "pipeline_id": str(i),
            "triggered_at": f"2024-01-01T00:00:{i % 60:02d}.{i:06d}+00:00",
        })
    lines = [l for l in (_tmp_data_dir / "ci_runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == MAX_ROWS
    # El más viejo (pipeline_id "0") fue rotado.
    ids = {json.loads(l)["pipeline_id"] for l in lines}
    assert "0" not in ids
    assert str(MAX_ROWS) in ids


def test_allowlist_descarta_extras(_tmp_data_dir):
    from services.ci_run_ledger import append_run

    append_run({"pipeline_id": "1", "password": "supersecret", "ref": "main"})
    text = (_tmp_data_dir / "ci_runs.jsonl").read_text(encoding="utf-8")
    assert "password" not in text
    assert "supersecret" not in text
    assert "\"pipeline_id\": \"1\"" in text


def test_lineas_corruptas_no_rompen(_tmp_data_dir):
    from services.ci_run_ledger import list_runs

    path = _tmp_data_dir / "ci_runs.jsonl"
    path.write_text(
        "{ esto no es json valido\n"
        + json.dumps({"pipeline_id": "ok", "triggered_at": "2024-01-01T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    runs = list_runs()
    assert len(runs) == 1
    assert runs[0]["pipeline_id"] == "ok"


def test_runs_no_captura_como_project(client, monkeypatch, _tmp_data_dir):
    """GET /api/ci/runs cae en la ruta nueva, no en /<project>/pipeline/... ni trigger."""
    monkeypatch.setattr(config.config, "STACKY_CI_RUN_LEDGER_ENABLED", True)
    resp = client.get("/api/ci/runs")
    assert resp.status_code == 200
    assert "runs" in resp.get_json()
