"""Plan 199 F2/F3 — Bitácora de lo no matcheado y sus endpoints HITL.

Una sesión de disco que no pertenece a ningún ticket no puede sumarse a los
números por ticket: iría a inflar el costo de trabajo que nunca hizo. Va a una
bitácora aparte, marcada como fuente propia.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import telemetry_harvest as H  # noqa: E402


@pytest.fixture
def datos(tmp_path, monkeypatch):
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(H, "data_dir", lambda: tmp_path, raising=False)
    # Un solo proyecto conocido, para poder distinguir atribuido de ajeno.
    proyectos = tmp_path / "projects"
    (proyectos / "RSPacifico").mkdir(parents=True)
    monkeypatch.setattr(runtime_paths, "projects_dir", lambda: proyectos)
    monkeypatch.setattr(runtime_paths, "repo_root", lambda: tmp_path / "Stacky")
    return tmp_path


def _run(session_id: str, hint: str | None = "RSPacifico", **over) -> H.HarvestedRun:
    base = dict(
        runtime="codex_cli", session_id=session_id, model="gpt-5",
        tokens_in=100, tokens_out=40, cache_read_tokens=0,
        total_cost_usd=None, cost_estimated=True,
        started_at=datetime(2026, 7, 1, 10, 0, 0),
        project_hint=hint, cwd=hint,
        artifact="rollout-x.jsonl", source_format="codex_rollout", num_events=2,
    )
    base.update(over)
    return H.HarvestedRun(**base)


def _lineas(datos) -> list:
    path = datos / "telemetry_harvest.jsonl"
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Bitácora
# ---------------------------------------------------------------------------

def test_append_dedup(datos):
    primero = H.append_to_ledger([_run("s1")], {}, attributed_only=True)
    segundo = H.append_to_ledger([_run("s1")], {}, attributed_only=True)

    assert primero["appended"] == 1
    assert segundo["appended"] == 0 and segundo["skipped_dup"] == 1
    assert len(_lineas(datos)) == 1


def test_append_skips_matched(datos):
    """Lo que ya se rellenó en la base no puede contarse dos veces."""
    run = _run("s1")

    resultado = H.append_to_ledger([run], {run.dedup_key(): 42}, attributed_only=True)

    assert resultado["appended"] == 0
    assert _lineas(datos) == []


def test_attributed_only_filters(datos):
    resultado = H.append_to_ledger([_run("s1", hint="ProyectoAjeno")], {},
                                   attributed_only=True)

    assert resultado["skipped_unattributed"] == 1
    assert _lineas(datos) == []


def test_sin_attributed_only_entra_todo(datos):
    resultado = H.append_to_ledger([_run("s1", hint="ProyectoAjeno")], {},
                                   attributed_only=False)

    assert resultado["appended"] == 1
    assert _lineas(datos)[0]["attributed"] is False, \
        "entra, pero marcada como no atribuida"


def test_sin_project_hint_no_se_atribuye(datos):
    """Conservador: marcar como propia una sesión sin señal metería gasto ajeno."""
    assert H._is_attributed(None, None) is False


def test_ledger_masks_artifact(datos):
    H.append_to_ledger([_run("s1", artifact="rollout-x.jsonl")], {},
                       attributed_only=True)

    linea = _lineas(datos)[0]
    assert "/" not in linea["artifact"] and "\\" not in linea["artifact"]


def test_dry_run_no_escribe(datos):
    resultado = H.append_to_ledger([_run("s1")], {}, attributed_only=True, dry_run=True)

    assert resultado["appended"] == 1 and resultado["dry_run"] is True
    assert _lineas(datos) == [], "un preview que escribe no es un preview"


def test_ledger_tolerates_corrupt_line(datos):
    H.append_to_ledger([_run("s1")], {}, attributed_only=True)
    path = datos / "telemetry_harvest.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "no soy json\n", encoding="utf-8")

    assert H.read_ledger_keys() == {"codex_cli:s1"}
    assert len(H.load_ledger_records()) == 1


# ---------------------------------------------------------------------------
# Reuso de los agregadores del 142
# ---------------------------------------------------------------------------

def test_load_ledger_records_shape(datos):
    from services import cost_analytics as ca

    H.append_to_ledger([_run("s1"), _run("s2")], {}, attributed_only=True)

    records = H.load_ledger_records()

    assert len(records) == 2
    assert all(r.execution_id < 0 for r in records), \
        "son sesiones sin ejecución: un id positivo chocaría con una real"
    resumen = ca.summarize(records)
    assert "billable_usd" in resumen
    assert "groups" in ca.breakdown(records, "runtime")


def test_ledger_started_at_naive_utc(datos):
    from services import cost_analytics as ca

    H.append_to_ledger([_run("s1", started_at=datetime(2026, 7, 1, 10, 0, 0))], {},
                       attributed_only=True)
    # Se reescribe con offset para simular una bitácora vieja con timestamps aware.
    path = datos / "telemetry_harvest.jsonl"
    doc = json.loads(path.read_text(encoding="utf-8").strip())
    doc["started_at"] = "2026-07-01T10:00:00+00:00"
    path.write_text(json.dumps(doc) + "\n", encoding="utf-8")

    records = H.load_ledger_records()

    assert records[0].started_at.tzinfo is None
    ca.summarize(records)   # no debe lanzar por mezclar naive con aware


def test_filtro_de_atribuidas_al_leer(datos):
    H.append_to_ledger([_run("s1", hint="ProyectoAjeno")], {}, attributed_only=False)

    assert H.load_ledger_records(source_attributed_only=True) == []
    assert len(H.load_ledger_records(source_attributed_only=False)) == 1


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def client(datos, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    # La base sqlite in-memory se comparte entre archivos de test: si quedaron
    # ejecuciones de otra suite con el mismo session_id, el backfill las matchea
    # y el run nunca llega a la bitácora. Acá se prueba justamente el caso
    # contrario, así que se parte de una base sin ejecuciones.
    from db import init_db, session_scope
    from models import AgentExecution

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def test_health_always_200(client):
    body = client.get("/api/metrics/telemetry-harvest/health").get_json()

    assert body["ok"] is True and isinstance(body["flag_enabled"], bool)


def test_scan_flag_off(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_TELEMETRY_HARVEST_ENABLED", False, raising=False)

    r = client.post("/api/metrics/telemetry-harvest/scan")

    assert r.status_code == 200 and r.get_json() == {"enabled": False}


def test_scan_disco_vacio_no_revienta(client, monkeypatch):
    monkeypatch.setattr(H, "harvest_runs", lambda **kw: [])

    body = client.post("/api/metrics/telemetry-harvest/scan").get_json()

    assert body["ok"] is True and body["discovered"] == 0


def test_scan_preview_es_el_default(client, monkeypatch, datos):
    """Sin apply=1 no se toca nada: esto muta filas históricas del operador."""
    monkeypatch.setattr(H, "harvest_runs", lambda **kw: [_run("s1")])

    body = client.post("/api/metrics/telemetry-harvest/scan").get_json()

    assert body["applied"] is False
    assert body["ledger"]["appended"] == 1
    assert _lineas(datos) == [], "el preview no puede haber escrito la bitácora"


def test_scan_apply_persiste(client, monkeypatch, datos):
    monkeypatch.setattr(H, "harvest_runs", lambda **kw: [_run("s1")])

    body = client.post("/api/metrics/telemetry-harvest/scan?apply=1").get_json()

    assert body["applied"] is True
    assert len(_lineas(datos)) == 1


def test_scan_no_da_500_con_artefacto_roto(client, monkeypatch):
    def _explota(**kw):
        raise RuntimeError("artefacto ilegible")

    monkeypatch.setattr(H, "harvest_runs", _explota)

    r = client.post("/api/metrics/telemetry-harvest/scan")

    assert r.status_code == 200 and r.get_json()["ok"] is False


def test_summary_invalid_dimension_400(client):
    r = client.get("/api/metrics/telemetry-harvest/summary?dimension=zzz")

    assert r.status_code == 400 and r.get_json()["error"] == "invalid_dimension"


def test_summary_reusa_los_agregadores(client, datos):
    H.append_to_ledger([_run("s1"), _run("s2")], {}, attributed_only=True)

    body = client.get("/api/metrics/telemetry-harvest/summary").get_json()

    assert body["ok"] is True
    assert "billable_usd" in body
    assert "groups" in body["breakdown"]
