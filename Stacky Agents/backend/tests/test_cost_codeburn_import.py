"""Plan 142 F7 (OPCIONAL) — Tests de load_external_codeburn() y su wiring en /cost-summary.

Flag STACKY_COST_CODEBURN_IMPORT_ENABLED default OFF (excepción dura #3: prerequisito
externo NO garantizado). Sin shell-out, sin dependencia nueva: sólo lectura de un JSONL
local opcional. Degrada a None en TODO caso de ausencia/error, nunca crashea.
"""
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


def test_disabled_returns_none(monkeypatch, tmp_path):
    from config import config as _cfg
    from services.cost_analytics import load_external_codeburn

    jsonl = tmp_path / "codeburn.jsonl"
    jsonl.write_text('{"cost_usd": 1.0}\n', encoding="utf-8")
    monkeypatch.setattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_ENABLED", False)
    monkeypatch.setattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_PATH", str(jsonl))

    assert load_external_codeburn() is None


def test_missing_path_returns_none(monkeypatch, tmp_path):
    from config import config as _cfg
    from services.cost_analytics import load_external_codeburn

    monkeypatch.setattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_ENABLED", True)
    monkeypatch.setattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_PATH", str(tmp_path / "does-not-exist.jsonl"))

    assert load_external_codeburn() is None

    # path vacío también -> None (desactivado).
    monkeypatch.setattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_PATH", "")
    assert load_external_codeburn() is None


def test_valid_jsonl_parsed(monkeypatch, tmp_path):
    from config import config as _cfg
    from services.cost_analytics import load_external_codeburn

    jsonl = tmp_path / "codeburn.jsonl"
    lines = [
        {"cost_usd": 1.5, "tokens_in": 100, "tokens_out": 20, "timestamp": "2026-07-01T00:00:00Z"},
        {"cost_usd": 2.25, "tokens_in": 200, "tokens_out": 40, "timestamp": "2026-07-02T00:00:00Z",
         "model": "claude-sonnet-5"},
    ]
    jsonl.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_ENABLED", True)
    monkeypatch.setattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_PATH", str(jsonl))

    result = load_external_codeburn()
    assert result is not None
    assert result["source"] == "external_jsonl"
    assert result["total_usd"] == 3.75
    assert result["records"] == 2


def test_malformed_jsonl_returns_none_no_crash(monkeypatch, tmp_path):
    from config import config as _cfg
    from services.cost_analytics import load_external_codeburn

    jsonl = tmp_path / "codeburn.jsonl"
    jsonl.write_text('{"cost_usd": 1.0}\nnot-json-at-all\n', encoding="utf-8")
    monkeypatch.setattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_ENABLED", True)
    monkeypatch.setattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_PATH", str(jsonl))

    assert load_external_codeburn() is None  # malformado -> None, NUNCA crash


@pytest.fixture(scope="module")
def _app():
    os.environ["STACKY_COST_CENTER_ENABLED"] = "true"
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def client(_app):
    with _app.test_client() as c:
        yield c


def test_summary_includes_reconciliation_when_enabled(client, monkeypatch, tmp_path):
    import config as config_module

    jsonl = tmp_path / "codeburn.jsonl"
    jsonl.write_text('{"cost_usd": 5.0}\n', encoding="utf-8")
    monkeypatch.setattr(config_module.config, "STACKY_COST_CODEBURN_IMPORT_ENABLED", True)
    monkeypatch.setattr(config_module.config, "STACKY_COST_CODEBURN_IMPORT_PATH", str(jsonl))

    resp = client.get("/api/metrics/cost-summary")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "external_reconciliation" in body
    ext = body["external_reconciliation"]
    assert ext["external_total_usd"] == 5.0
    assert ext["stacky_billable_usd"] == body["billable_usd"]
    assert ext["delta_usd"] == round(5.0 - body["billable_usd"], 6)

    # Flag OFF -> la clave NO aparece (silencio total).
    monkeypatch.setattr(config_module.config, "STACKY_COST_CODEBURN_IMPORT_ENABLED", False)
    resp2 = client.get("/api/metrics/cost-summary")
    assert "external_reconciliation" not in resp2.get_json()
