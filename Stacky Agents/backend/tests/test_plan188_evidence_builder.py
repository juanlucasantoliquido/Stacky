"""tests/test_plan188_evidence_builder.py — Plan 188 F1.

El builder determinista convierte el ledger entry fallido en el paquete
completo (summary + markdown + JSON), sin secretos (dos capas: claves +
valores con pinta de token), con caps respetados y sin red (KPI-1..KPI-3).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXED_NOW = datetime(2026, 7, 18, tzinfo=timezone.utc)

# Literal partido a propósito (gotcha push-protection GitHub): un valor con
# pinta de token dentro del stdout del paso fallido.
_TOKEN_VALUE = "ghp_" + "x" * 20
_APP = {"id": "miapp", "name": "MiApp"}


def _golden_ledger():
    # el token va en una línea DENTRO de la cola (últimas 60) para verificar el
    # masking tanto en el markdown (que sólo muestra la cola) como en el JSON.
    stdout_200 = "\n".join(f"stdout line {i} {_TOKEN_VALUE}" if i == 195 else f"stdout line {i}"
                           for i in range(200))
    golden = {
        "run_id": "dr-golden-1",
        "app_id": "miapp",
        "target": "__local__",
        "action": "deploy",
        "version_id": "1.4.2",
        "status": "failed_smoke",
        "started_at": "2026-07-18T10:00:00+00:00",
        "finished_at": "2026-07-18T10:01:00+00:00",
        "duration_ms": 60000,
        "steps": [
            {"name": "transfer", "ok": True, "ms": 100, "detail": ""},
            {"name": "activate", "ok": False, "ms": 200, "detail": "boom",
             "stdout": stdout_200, "stderr": "traceback here"},
            {"name": "prune", "ok": True, "ms": 50, "detail": ""},
        ],
        "smoke": {"kind": "http", "ok": False, "detail": "status=500"},
        # secretos por CLAVE, anidados en el entry (deben quedar "<omitido>"):
        "source": {"kind": "folder", "path": "C:\\build\\miapp",
                   "DEPLOY_TOKEN": "supersecretdeploytoken",
                   "DB_PASSWORD": "pgpasswordvalue"},
    }
    prev2 = {"run_id": "dr-prev-2", "app_id": "miapp", "target": "__local__",
             "action": "deploy", "status": "success", "version_id": "1.4.1",
             "started_at": "2026-07-17T09:00:00+00:00"}
    prev3 = {"run_id": "dr-prev-3", "app_id": "miapp", "target": "__local__",
             "action": "deploy", "status": "failed", "version_id": "1.4.0",
             "started_at": "2026-07-16T08:00:00+00:00"}
    return [golden, prev2, prev3]  # más recientes primero


def _install(monkeypatch, ledger, app=_APP):
    from services import deploy_store

    def _read_ledger(app_id=None, target=None, limit=100):
        rows = list(ledger)
        if app_id is not None:
            rows = [r for r in rows if r.get("app_id") == app_id]
        if target is not None:
            rows = [r for r in rows if r.get("target") == target]
        return rows[:limit]

    monkeypatch.setattr(deploy_store, "read_ledger", _read_ledger)
    monkeypatch.setattr(deploy_store, "get_app", lambda aid: app if app and app.get("id") == aid else None)


def _build(**kw):
    from services.devops_evidence import build_deploy_failure_evidence
    return build_deploy_failure_evidence("miapp", "__local__", kw.pop("run_id", "dr-golden-1"),
                                         now=kw.pop("now", FIXED_NOW))


def test_none_si_run_inexistente(monkeypatch):
    _install(monkeypatch, _golden_ledger())
    assert _build(run_id="nope") is None


def test_summary_formato_y_cap_120(monkeypatch):
    _install(monkeypatch, _golden_ledger())
    b = _build()
    assert b.summary.startswith("Despliegue fallido: MiApp → __local__ (failed_smoke, v1.4.2)")
    assert len(b.summary) <= 120


def test_summary_truncado_a_120(monkeypatch):
    ledger = _golden_ledger()
    b = _build_with_app(monkeypatch, ledger, {"id": "miapp", "name": "N" * 200})
    assert len(b.summary) <= 120
    assert b.summary.endswith("…")


def _build_with_app(monkeypatch, ledger, app):
    _install(monkeypatch, ledger, app=app)
    return _build()


def test_kpi1_determinista_y_sin_red(monkeypatch):
    import socket

    def _boom(*a, **k):
        raise AssertionError("la evidencia NO debe tocar la red")

    _install(monkeypatch, _golden_ledger())
    monkeypatch.setattr(socket, "socket", _boom)
    t0 = time.time()
    b1 = _build()
    b2 = _build()
    dt = time.time() - t0
    assert b1.to_dict() == b2.to_dict()
    assert dt < 0.1


def test_kpi2_cero_secretos(monkeypatch):
    _install(monkeypatch, _golden_ledger())
    b = _build()
    blob = b.markdown + "\n" + b.modal_text + "\n" + json.dumps(b.json_payload, ensure_ascii=False)
    assert "supersecretdeploytoken" not in blob
    assert "pgpasswordvalue" not in blob
    assert _TOKEN_VALUE not in blob
    # la clave se preserva pero su valor es "<omitido>"
    src = b.json_payload["run"]["source"]
    assert src["DEPLOY_TOKEN"] == "<omitido>"
    assert src["DB_PASSWORD"] == "<omitido>"


def test_mask_token_values_en_stdout(monkeypatch):
    _install(monkeypatch, _golden_ledger())
    b = _build()
    assert "<posible-secreto-omitido>" in b.markdown
    assert _TOKEN_VALUE not in json.dumps(b.json_payload, ensure_ascii=False)


def test_tail_60_lineas(monkeypatch):
    _install(monkeypatch, _golden_ledger())
    b = _build()
    # el stdout de 200 líneas queda recortado (marca de truncado en el markdown)
    assert "… (truncado)" in b.markdown
    # la última línea del stdout (199) sí sobrevive, la primera (0) no
    assert "stdout line 199" in b.markdown
    assert "stdout line 0\n" not in b.markdown


def test_fallo_por_smoke_sin_step_fallido(monkeypatch):
    ledger = _golden_ledger()
    entry = ledger[0]
    for s in entry["steps"]:
        s["ok"] = True
    entry["smoke"] = {"kind": "http", "ok": False, "detail": "status=503"}
    _install(monkeypatch, ledger)
    b = _build()
    assert "Falló el smoke" in b.markdown
    assert b.json_payload["failed_step"]["name"] == "smoke"


def test_sin_paso_fallido_identificado(monkeypatch):
    ledger = _golden_ledger()
    entry = ledger[0]
    for s in entry["steps"]:
        s["ok"] = True
    entry["smoke"] = {"kind": "http", "ok": True, "detail": "status=200"}
    entry["status"] = "success"
    _install(monkeypatch, ledger)
    b = _build()  # no debe levantar excepción (C5)
    assert "No se identificó un paso fallido" in b.markdown
    assert b.json_payload["failed_step"] is None


def test_footer_trazabilidad(monkeypatch):
    _install(monkeypatch, _golden_ledger())
    b = _build()
    expected = f"_Generado por Stacky · evidencia 188.1 · {FIXED_NOW.isoformat()}_"
    assert b.markdown.rstrip().endswith(expected)


def test_secciones_markdown_exactas(monkeypatch):
    _install(monkeypatch, _golden_ledger())
    b = _build()
    order = ["## Resumen", "## Paso fallido", "## Smoke",
             "## Historial reciente", "## Siguientes pasos sugeridos"]
    positions = [b.markdown.find(h) for h in order]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions)


def test_historial_reciente_excluye_run_propio(monkeypatch):
    _install(monkeypatch, _golden_ledger())
    b = _build()
    prev = b.json_payload["previous_runs"]
    ids = [p["run_id"] for p in prev]
    assert "dr-golden-1" not in ids
    assert ids == ["dr-prev-2", "dr-prev-3"]
    assert b.json_payload["last_success_version"] == "1.4.1"


def test_kpi3_caps_con_run_gigante(monkeypatch):
    big = "x" * 3_000_000
    giant = {
        "run_id": "dr-giant", "app_id": "miapp", "target": "__local__",
        "action": "deploy", "version_id": "9.9.9", "status": "failed",
        "started_at": "2026-07-18T10:00:00+00:00", "duration_ms": 1000,
        "steps": [{"name": "activate", "ok": False, "ms": 10, "detail": "boom",
                   "stdout": big, "stderr": big}],
        "smoke": None,
    }
    _install(monkeypatch, [giant])
    b = _build(run_id="dr-giant")
    assert len(b.summary) <= 120
    assert len(b.modal_text) <= 18_000
    assert len(b.markdown) <= 100_000
    assert len(json.dumps(b.json_payload, ensure_ascii=False).encode("utf-8")) <= 1_000_000


def test_sin_imports_de_red():
    src = Path(ROOT / "services" / "devops_evidence.py").read_text(encoding="utf-8")
    assert "import requests" not in src
    assert "remote_exec" not in src
    assert "ci_variables" not in src
