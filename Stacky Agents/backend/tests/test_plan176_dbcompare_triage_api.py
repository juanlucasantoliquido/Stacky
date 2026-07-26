"""Plan 176 F1 — Endpoints del triage y `item_key` emitida antes del enmascarado."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_RUN = "run_plan176_src_vs_dst"
_BASE = f"/api/db-compare/runs/{_RUN}/triage"


def _run_doc(status: str = "done") -> dict:
    from datetime import datetime, timezone

    return {
        "run_id": _RUN,
        "status": status,
        # Los runs reales siempre lo traen; _is_stale lo exige para los no-done.
        "started_at": datetime.now(timezone.utc).isoformat(),
        "source_alias": "src",
        "target_alias": "dst",
        "diff": {"items": [
            {"object_type": "table", "schema": "dbo", "name": "RCONTROLES",
             "severity": "alta", "change": "missing_in_target"},
            {"object_type": "view", "schema": "dbo", "name": "V_X",
             "severity": "media", "change": "different"},
        ]},
        "data_diff": {"tables": {"dbo.RCONTROLES": {
            "schema": "dbo", "table": "RCONTROLES", "pk_cols": ["clave"],
            "columns": ["clave", "password"],
            "column_types": {"clave": "varchar", "password": "varchar"},
            "only_source": [{"clave": "SECRETO-1", "password": "hunter2"}],
            "only_target": [],
            "changed": [],
        }}},
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    import runtime_paths
    from services import dbcompare_runs, dbcompare_triage

    datos = tmp_path / "data"
    (datos / "db_compare" / "runs").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: datos)
    monkeypatch.setattr(dbcompare_runs, "data_dir", lambda: datos, raising=False)
    monkeypatch.setattr(dbcompare_triage, "_triage_dir",
                        lambda: datos / "db_compare" / "triage")

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        c._datos = datos
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def _sembrar(client, status: str = "done") -> None:
    destino = client._datos / "db_compare" / "runs" / f"{_RUN}.json"
    destino.write_text(json.dumps(_run_doc(status), ensure_ascii=False),
                       encoding="utf-8")


def test_triage_403_si_flag_off(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DB_COMPARE_TRIAGE_ENABLED", False, raising=False)
    _sembrar(client)

    assert client.get(_BASE).status_code == 403
    assert client.put(f"{_BASE}/item", json={}).status_code == 403
    assert client.get(f"{_BASE}/exclusions.md").status_code == 403


def test_get_triage_404_run_inexistente(client):
    assert client.get("/api/db-compare/runs/no_existe/triage").status_code == 404


def test_get_triage_vacio_trae_summary(client):
    _sembrar(client)

    body = client.get(_BASE).get_json()

    assert body["items"] == {}
    assert body["summary"] == {"confirmado": 0, "excluido": 0, "pendiente": 2}


def test_put_decision_y_get_roundtrip(client):
    _sembrar(client)

    r = client.put(f"{_BASE}/item", json={
        "item_key": "table:dbo.RCONTROLES", "decision": "excluido",
        "note": "ya la migramos a mano",
    })

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["summary"] == {"confirmado": 0, "excluido": 1, "pendiente": 1}

    leido = client.get(_BASE).get_json()
    assert leido["items"]["table:dbo.RCONTROLES"]["note"] == "ya la migramos a mano"


def test_put_decision_invalida_400(client):
    _sembrar(client)

    r = client.put(f"{_BASE}/item", json={
        "item_key": "table:dbo.RCONTROLES", "decision": "mas_o_menos"})

    assert r.status_code == 400
    assert r.get_json()["error"] == "decision_invalida"


def test_put_item_key_desconocida_404(client):
    _sembrar(client)

    r = client.put(f"{_BASE}/item", json={
        "item_key": "table:dbo.NO_EXISTE", "decision": "excluido"})

    assert r.status_code == 404
    assert r.get_json()["error"] == "item_desconocido"


def test_put_run_no_done_409(client):
    """Decidir sobre un diff que todavía se está calculando no tiene sentido."""
    _sembrar(client, status="running")

    r = client.put(f"{_BASE}/item", json={
        "item_key": "table:dbo.RCONTROLES", "decision": "confirmado"})

    assert r.status_code == 409
    assert r.get_json()["error"] == "run_no_done"


def test_put_item_de_datos_se_acepta_por_tabla(client):
    _sembrar(client)

    r = client.put(f"{_BASE}/item", json={
        "item_key": 'data:dbo.RCONTROLES:{"clave":"SECRETO-1"}',
        "decision": "confirmado"})

    assert r.status_code == 200, r.get_json()


def test_put_item_de_tabla_ajena_404(client):
    _sembrar(client)

    r = client.put(f"{_BASE}/item", json={
        "item_key": 'data:dbo.OTRA:{"clave":"1"}', "decision": "confirmado"})

    assert r.status_code == 404


def test_exclusions_md_lista_notas(client):
    _sembrar(client)
    client.put(f"{_BASE}/item", json={
        "item_key": "view:dbo.V_X", "decision": "excluido", "note": "vista obsoleta"})

    r = client.get(f"{_BASE}/exclusions.md")

    assert r.status_code == 200
    assert "attachment" in r.headers["Content-Disposition"]
    cuerpo = r.get_data(as_text=True)
    assert "view:dbo.V_X" in cuerpo and "vista obsoleta" in cuerpo


def test_exclusions_md_sin_exclusiones(client):
    _sembrar(client)

    assert "Sin exclusiones." in client.get(f"{_BASE}/exclusions.md").get_data(as_text=True)


def test_get_run_expone_item_key_pre_masking(client, monkeypatch):
    """El masking tapa la PK: si la key se calculara después, sería inservible."""
    from config import config as cfg
    from services import dbcompare_triage

    monkeypatch.setattr(cfg, "STACKY_DB_COMPARE_MASKING_ENABLED", True, raising=False)
    _sembrar(client)

    body = client.get(f"/api/db-compare/runs/{_RUN}").get_json()

    assert body["diff"]["items"][0]["item_key"] == "table:dbo.RCONTROLES"
    fila = body["data_diff"]["tables"]["dbo.RCONTROLES"]["only_source"][0]
    esperada = dbcompare_triage.item_key_for_data_row(
        "dbo", "RCONTROLES", {"clave": "SECRETO-1"})
    assert fila["item_key"] == esperada, \
        "la item_key debe calcularse sobre el valor REAL, no sobre el enmascarado"
