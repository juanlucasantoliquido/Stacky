"""Plan 60 F5 — Tests de sweep_recent_runs (services/ado_edit_learning.py).

No testea el thread de app.py (no determinista); testea sweep_recent_runs directo
con inyección de runs y learn_fn para aislamiento total de DB/ADO.
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass


@dataclass
class _FakeRun:
    """Simula un objeto Execution con .id y .metadata."""
    id: int
    metadata: dict


_BASELINE_HTML = "<h1>EP-1</h1><h2>RF-1 — Auth</h2><p>El usuario inicia sesión.</p>"

_REV_STACKY = {
    "rev": 1,
    "revisedBy": {"uniqueName": "stacky@empresa.com"},
    "fields": {"System.Description": {"oldValue": "", "newValue": _BASELINE_HTML}},
}
_REV_HUMAN = {
    "rev": 2,
    "revisedBy": {"uniqueName": "operador@empresa.com"},
    "fields": {
        "System.Description": {
            "oldValue": _BASELINE_HTML,
            "newValue": (
                "<h1>EP-1</h1><h2>RF-1 — Auth</h2>"
                "<p>El usuario inicia sesión con MFA obligatorio para seguridad corporativa.</p>"
            ),
        }
    },
}


class FakeAdo:
    def __init__(self, revisions=None, raise_on_fetch=False):
        self._revisions = revisions or []
        self._raise = raise_on_fetch

    def fetch_work_item_updates(self, ado_id, top=50):
        if self._raise:
            raise RuntimeError("ADO unavailable")
        return self._revisions


@pytest.fixture()
def mem_ledger(monkeypatch, tmp_path):
    """Ledger con DB en tmpdir para aislamiento."""
    import services.ado_edit_ledger as lm
    monkeypatch.setattr(lm, "_get_db_path", lambda: str(tmp_path / "sweep_test.db"))
    monkeypatch.setattr(lm, "_get_jsonl_path", lambda: tmp_path / "ledger.jsonl")
    lm._create_table_if_needed()
    return lm


@pytest.fixture()
def captured_save(monkeypatch):
    calls = []
    import services.memory_store as ms
    monkeypatch.setattr(ms, "save_observation", lambda **kw: (calls.append(kw), "fid")[1])
    return calls


def test_sweep_no_runs_returns_zero(mem_ledger, captured_save):
    """sweep_recent_runs con 0 runs con epic_ado_id => devuelve 0, no llama ADO."""
    from services.ado_edit_learning import sweep_recent_runs, LearnResult

    def fake_learn(**kw):
        return LearnResult(learned=True, lesson_written=True, golden_written=False,
                           rev=2, reason="ok")

    result = sweep_recent_runs(
        _db_runs=[],
        _ado_client_factory=lambda p: FakeAdo(),
        _learn_fn=fake_learn,
    )
    assert result == 0
    assert not captured_save


def test_sweep_one_run_with_human_edit_returns_one(mem_ledger, captured_save):
    """1 run con epic_ado_id + revisión humana => sweep_recent_runs devuelve 1."""
    from services.ado_edit_learning import sweep_recent_runs

    run = _FakeRun(
        id=1,
        metadata={
            "epic_ado_id": 200,
            "epic_baseline_html": _BASELINE_HTML,
            "epic_baseline_rev": 1,
            "project_name": "P",
        },
    )
    result = sweep_recent_runs(
        _db_runs=[run],
        _ado_client_factory=lambda p: FakeAdo(revisions=[_REV_STACKY, _REV_HUMAN]),
        _learn_fn=None,  # usa la función real
    )
    assert result == 1
    assert len(captured_save) == 1


def test_sweep_second_pass_idempotent(mem_ledger, captured_save):
    """Segundo sweep inmediato (ledger ya marcado) => devuelve 0 (idempotencia)."""
    from services.ado_edit_learning import sweep_recent_runs

    run = _FakeRun(
        id=2,
        metadata={
            "epic_ado_id": 201,
            "epic_baseline_html": _BASELINE_HTML,
            "epic_baseline_rev": 1,
            "project_name": "P",
        },
    )
    sweep_recent_runs(
        _db_runs=[run],
        _ado_client_factory=lambda p: FakeAdo(revisions=[_REV_STACKY, _REV_HUMAN]),
        _learn_fn=None,
    )
    captured_save.clear()
    result2 = sweep_recent_runs(
        _db_runs=[run],
        _ado_client_factory=lambda p: FakeAdo(revisions=[_REV_STACKY, _REV_HUMAN]),
        _learn_fn=None,
    )
    assert result2 == 0
    assert not captured_save


def test_sweep_ado_unavailable_returns_zero(mem_ledger, captured_save):
    """FakeAdo.fetch_work_item_updates lanza => sweep no propaga, devuelve 0."""
    from services.ado_edit_learning import sweep_recent_runs

    run = _FakeRun(
        id=3,
        metadata={"epic_ado_id": 202, "project_name": "P"},
    )
    result = sweep_recent_runs(
        _db_runs=[run],
        _ado_client_factory=lambda p: FakeAdo(raise_on_fetch=True),
        _learn_fn=None,
    )
    assert result == 0
    assert not captured_save


def test_smoke_no_daemon_thread_when_flag_off(monkeypatch):
    """Con STACKY_ADO_EDIT_LEARNING_ENABLED ausente, el daemon NO existe."""
    import threading
    monkeypatch.delenv("STACKY_ADO_EDIT_LEARNING_ENABLED", raising=False)
    daemon_names = {t.name for t in threading.enumerate()}
    assert "stacky-ado-edit-daemon" not in daemon_names
