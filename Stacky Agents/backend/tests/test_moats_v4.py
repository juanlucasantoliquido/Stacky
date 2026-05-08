"""Tests de Fase 4: FA-07, FA-15, FA-16, FA-25, FA-44."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


# ── FA-07 release context ────────────────────────────────────

def test_fa07_no_env_returns_none_block():
    os.environ.pop("NEXT_RELEASE_DATE", None)
    os.environ.pop("RELEASE_FREEZE_DATE", None)
    from services import release_context
    block = release_context.build_context_block()
    assert block is None


def test_fa07_with_env_returns_block():
    os.environ["NEXT_RELEASE_DATE"] = "2026-12-01"
    os.environ["RELEASE_FREEZE_DATE"] = "2026-11-29"
    from importlib import reload
    from services import release_context
    reload(release_context)
    info = release_context.get_release_info()
    assert info.next_release == "2026-12-01"
    assert info.policy in {"normal", "soft-freeze", "hard-freeze"}
    block = release_context.build_context_block()
    assert block is not None and "Próxima release" in block["content"]
    os.environ.pop("NEXT_RELEASE_DATE")
    os.environ.pop("RELEASE_FREEZE_DATE")


def test_fa07_endpoint(client):
    r = client.get("/api/release/context")
    assert r.status_code == 200
    d = r.get_json()
    assert "policy" in d


# ── FA-15 glossary builder ───────────────────────────────────

def test_fa15_scan_empty_returns_zero():
    from services import glossary_builder
    count = glossary_builder.scan_approved(days=1, min_occurrences=99)
    assert count == 0


def test_fa15_extract_terms_from_output():
    from services.glossary_builder import _extract_from
    text = "La clase **CobranzaService** y el método `ProcessPayment` manejan RIDIOMA."
    raws = _extract_from(text, exec_id=1)
    terms = {r.term for r in raws}
    assert "CobranzaService" in terms or "ProcessPayment" in terms


def test_fa15_list_entries_endpoint(client):
    r = client.get("/api/glossary/entries")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_fa15_scan_endpoint(client):
    r = client.post("/api/glossary/candidates/scan", json={"days": 30})
    assert r.status_code == 200
    assert "new_candidates" in r.get_json()


# ── FA-16 drift detection ────────────────────────────────────

def test_fa16_run_detection_empty_no_crash(client):
    r = client.post("/api/drift/run", json={"window_days": 7, "min_sample": 3})
    assert r.status_code == 200
    d = r.get_json()
    assert "alerts_generated" in d


def test_fa16_list_alerts_empty(client):
    r = client.get("/api/drift/alerts")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_fa16_thresholds_defined():
    from services.drift_detector import THRESHOLDS
    # Bajada de approval_rate 0.90→0.60 debe superar umbral critical
    delta = 0.60 - 0.90  # -0.30
    assert delta <= THRESHOLDS["approval_rate"]["critical"]
    # Subida de error_rate 0.05→0.25 debe superar umbral critical
    delta_err = 0.25 - 0.05  # +0.20
    assert delta_err >= THRESHOLDS["error_rate"]["critical"]


# ── FA-25 bookmarklet ────────────────────────────────────────

def test_fa25_context_inbox_creates_block(client):
    payload = {
        "url": "https://confluence.example.com/page/123",
        "title": "Spec de cobranzas",
        "selection": "El módulo de cobranzas debe procesar pagos en < 2s.",
    }
    r = client.post("/api/context/inbox", json=payload)
    assert r.status_code == 200
    d = r.get_json()
    assert "block" in d
    assert d["block"]["kind"] == "auto"
    assert "cobranzas" in d["block"]["content"]


def test_fa25_context_inbox_requires_selection(client):
    r = client.post("/api/context/inbox", json={"url": "https://x.com", "selection": ""})
    assert r.status_code == 400


def test_fa25_bookmarklet_js_endpoint(client):
    r = client.get("/api/context/bookmarklet.js")
    assert r.status_code == 200
    assert "fetch" in r.data.decode()
    assert "context/inbox" in r.data.decode()


# ── FA-44 sandbox seed ───────────────────────────────────────

def test_fa44_seed_sandbox_script():
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "scripts/seed_sandbox.py"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "DATABASE_URL": "sqlite:///:memory:"},
    )
    assert result.returncode == 0
    assert "__sandbox__" in result.stdout or "OK" in result.stdout
