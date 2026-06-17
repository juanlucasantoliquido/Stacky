"""V2.3 — Modos del gate de import: off | warn | block."""
from __future__ import annotations

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


class _FakeEntry:
    def __init__(self, path: Path):
        self.filename = path.name
        self.path = str(path)

    def to_manifest_dict(self):
        return {"filename": self.filename}


@pytest.fixture
def fake_import(monkeypatch, tmp_path):
    """Monkeypatcha import_agent_from_path para escribir en el canonical real
    (con nombre único) y devolver una entry falsa. Limpia al final."""
    from services import stacky_agents as svc

    canonical = svc.stacky_agents_dir()
    canonical.mkdir(parents=True, exist_ok=True)
    dest = canonical / "ZZGateModeTest_developer.agent.md"

    def _fake(src, overwrite=False):
        dest.write_text("# nuevo prompt importado\n", encoding="utf-8")
        return _FakeEntry(dest)

    monkeypatch.setattr(svc, "import_agent_from_path", _fake)
    # source_path no necesita existir (import está monkeypatcheado)
    yield {"dest": dest, "source_path": str(tmp_path / "ZZGateModeTest_developer.agent.md")}
    if dest.exists():
        dest.unlink()


def _post(client, source_path):
    return client.post("/api/agents/stacky/import", json={"source_path": source_path, "overwrite": True})


def test_off_mode_skips_gate(client, fake_import, monkeypatch):
    import evals.eval_gate as gate
    monkeypatch.setenv("STACKY_EVAL_GATE_MODE", "off")
    monkeypatch.setattr(gate, "run_evals_for_agent_type", lambda _t: (_ for _ in ()).throw(AssertionError("no debe correr")))

    r = _post(client, fake_import["source_path"])
    assert r.status_code == 200
    assert r.get_json()["evals_warning"] is None


def test_warn_mode_returns_warning_but_does_not_block(client, fake_import, monkeypatch):
    import evals.eval_gate as gate
    monkeypatch.setenv("STACKY_EVAL_GATE_MODE", "warn")
    monkeypatch.setattr(gate, "run_evals_for_agent_type", lambda _t: "[eval-gate] 1 golden falló")

    r = _post(client, fake_import["source_path"])
    assert r.status_code == 200
    assert "golden falló" in r.get_json()["evals_warning"]
    assert fake_import["dest"].exists()  # warn no revierte


def test_block_mode_rejects_and_reverts_new_file(client, fake_import, monkeypatch):
    import evals.eval_gate as gate
    monkeypatch.setenv("STACKY_EVAL_GATE_MODE", "block")
    monkeypatch.setattr(gate, "run_evals_for_agent_type", lambda _t: "[eval-gate] 2 goldens fallaron")

    r = _post(client, fake_import["source_path"])
    assert r.status_code == 409
    assert r.get_json()["error"] == "eval_gate_blocked"
    # Archivo nuevo → revertido (borrado).
    assert not fake_import["dest"].exists()


def test_block_mode_allows_when_goldens_pass(client, fake_import, monkeypatch):
    import evals.eval_gate as gate
    monkeypatch.setenv("STACKY_EVAL_GATE_MODE", "block")
    monkeypatch.setattr(gate, "run_evals_for_agent_type", lambda _t: None)

    r = _post(client, fake_import["source_path"])
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert fake_import["dest"].exists()
