"""Plan 158 — Tests de paridad de telemetría de costo en claude_code_cli_runner.

F0: estos tests fallan HOY (services.claude_code_cli_runner._finalize_cost_telemetry
no existe todavía) y deben pasar después de F1+F3.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import db  # noqa: E402

# C1 (v2) — crear las tablas en la DB in-memory compartida ANTES de cualquier
# session_scope. Sin esto, los tests de backfill fallan SIEMPRE con
# "no such table" (el conftest.py de tests sólo setea STACKY_TEST_MODE, no
# inicializa DB). Patrón existente: test_plan117_insights_api.py:16-27.
db.init_db()


def _make_fake_scope(fake_row):
    class _FakeSession:
        def get(self, model, eid):
            return fake_row

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return _FakeSession


# ---------------------------------------------------------------------------
# F1 — unidad: _finalize_cost_telemetry
# ---------------------------------------------------------------------------

def test_finalize_cost_telemetry_sets_model_key_unconditionally():
    from services import claude_code_cli_runner as r

    metadata = {"runtime": "claude_code_cli", "claude_code_model": "claude-sonnet-4-6"}
    # stream_telemetry vacío (proceso matado antes de cualquier evento result) —
    # aun así "model" debe quedar seteado (Defecto A, independiente del stall).
    r._finalize_cost_telemetry(
        execution_id=1, metadata=metadata, stream_telemetry={},
        routed_model="claude-sonnet-4-6",
    )
    assert metadata["model"] == "claude-sonnet-4-6"


def test_finalize_cost_telemetry_skips_persist_when_stream_empty(monkeypatch):
    from services import claude_code_cli_runner as r
    import harness.telemetry as ht_mod

    calls = []
    monkeypatch.setattr(ht_mod, "persist", lambda eid, t: calls.append((eid, t)))

    metadata = {"runtime": "claude_code_cli", "claude_code_model": "claude-sonnet-4-6"}
    r._finalize_cost_telemetry(
        execution_id=1, metadata=metadata, stream_telemetry={},
        routed_model="claude-sonnet-4-6",
    )
    assert calls == []


def test_finalize_cost_telemetry_persists_harness_telemetry_when_stream_has_data(monkeypatch):
    from services import claude_code_cli_runner as r
    import harness.telemetry as ht_mod

    fake_row = type("R", (), {"metadata_dict": {}})()
    FakeSession = _make_fake_scope(fake_row)
    monkeypatch.setattr(ht_mod, "session_scope", lambda: FakeSession())

    metadata = {"runtime": "claude_code_cli", "claude_code_model": "claude-sonnet-4-6"}
    stream_telemetry = {
        "session_id": "sess-plan158",
        "num_turns": 3,
        "is_error": False,
        "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
        # SIN total_cost_usd — el caso que hoy rompe (Defecto A+B).
    }
    r._finalize_cost_telemetry(
        execution_id=1, metadata=metadata, stream_telemetry=stream_telemetry,
        routed_model="claude-sonnet-4-6",
    )
    assert "harness_telemetry" in fake_row.metadata_dict
    ht = fake_row.metadata_dict["harness_telemetry"]
    assert ht["cost_estimated"] is True
    assert ht["total_cost_usd"] == 18.0  # 1M*3 + 1M*15 USD/Mtok (claude-sonnet-4 en harness/pricing.py)


def test_finalize_cost_telemetry_never_raises_on_persist_failure(monkeypatch):
    from services import claude_code_cli_runner as r
    import harness.telemetry as ht_mod

    def _boom(eid, t):
        raise RuntimeError("db down")

    monkeypatch.setattr(ht_mod, "persist", _boom)
    metadata = {"runtime": "claude_code_cli", "claude_code_model": "claude-sonnet-4-6"}
    # No debe lanzar excepción (paridad con el try/except de codex_cli_runner.py:808-817).
    r._finalize_cost_telemetry(
        execution_id=1, metadata=metadata,
        stream_telemetry={"usage": {"input_tokens": 10, "output_tokens": 10}},
        routed_model="claude-sonnet-4-6",
    )
    assert metadata["model"] == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# F1+F3 — end-to-end: metadata final (persist + merge de _mark_terminal) ->
# extract_cost_row() ya NO es "unknown".
# ---------------------------------------------------------------------------

def test_finalize_cost_telemetry_then_merge_yields_estimated_cost(monkeypatch):
    """Simula el flujo real: persist() escribe harness_telemetry en la fila
    directamente; _mark_terminal (claude_code_cli_runner.py:2894-2895) después
    hace `current_md.update(metadata)`. Replicamos ambos pasos y verificamos
    que extract_cost_row() de la unión ya no es unknown."""
    from services import claude_code_cli_runner as r
    from services.cost_analytics import extract_cost_row
    import harness.telemetry as ht_mod

    fake_row = type("R", (), {"metadata_dict": {}})()
    FakeSession = _make_fake_scope(fake_row)
    monkeypatch.setattr(ht_mod, "session_scope", lambda: FakeSession())

    stream_telemetry = {
        "session_id": "sess-plan158",
        "num_turns": 3,
        "is_error": False,
        "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
    }
    metadata = {"runtime": "claude_code_cli", "claude_code_model": "claude-sonnet-4-6"}

    r._finalize_cost_telemetry(
        execution_id=1, metadata=metadata, stream_telemetry=stream_telemetry,
        routed_model="claude-sonnet-4-6",
    )

    # Simula el merge de _mark_terminal: current_md.update(metadata).
    final_md = dict(fake_row.metadata_dict)
    final_md.update(metadata)

    row = extract_cost_row(final_md)
    assert row.model == "claude-sonnet-4-6"
    assert row.cost_kind == "estimated"
    assert row.cost_usd == 18.0


def test_baseline_without_fix_is_unknown_documents_the_bug():
    """Ancla el ANTES: la metadata que produce el runner HOY (sin "model", sin
    harness_telemetry, sólo claude_telemetry con usage y sin total_cost_usd)
    es "unknown" en el extractor canónico. Este test debe seguir en verde
    ANTES y DESPUÉS del fix (documenta el bug, no lo reproduce como red)."""
    from services.cost_analytics import extract_cost_row

    md_hoy_sin_fix = {
        "runtime": "claude_code_cli",
        "claude_code_model": "claude-sonnet-4-6",  # clave vieja, extract_cost_row no la lee
        "claude_telemetry": {"usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000}},
        # sin "model", sin "harness_telemetry"
    }
    row = extract_cost_row(md_hoy_sin_fix)
    assert row.cost_kind == "unknown"
    assert row.cost_usd is None


def test_runtime_parity_matrix_no_unknown():
    """[ADICIÓN ARQUITECTO v2] Matriz de paridad de los 3 runtimes en UN test.

    La metadata canónica que cada runner produce POST-fix debe dar
    cost_kind != "unknown" en el extractor. Es la red de regresión permanente
    contra la clase exacta de bug de este plan: un runner que deriva de las
    claves canónicas. Verde ANTES y DESPUÉS del fix (el extractor ya soporta
    estas formas; el bug era que claude_code_cli no las PRODUCÍA)."""
    from services.cost_analytics import extract_cost_row

    matrix = {
        # claude_code_cli post-F3: model top-level + claude_telemetry.usage sin costo
        "claude_code_cli": {
            "runtime": "claude_code_cli",
            "model": "claude-sonnet-4-6",
            "claude_telemetry": {"usage": {"input_tokens": 1000, "output_tokens": 1000}},
        },
        # codex_cli (ya correcto hoy): harness_telemetry persistido con costo estimado
        "codex_cli": {
            "runtime": "codex_cli",
            "harness_telemetry": {
                "runtime": "codex_cli", "total_cost_usd": 0.5, "cost_estimated": True,
                "input_tokens": 1000, "output_tokens": 1000,
            },
        },
        # github_copilot (ya correcto hoy, §2.4): claves canónicas del bridge
        "github_copilot": {
            "runtime": "github_copilot",
            "model": "claude-sonnet-4-6",
            "tokens_in": 1000,
            "tokens_out": 1000,
        },
    }
    expected_kind = {
        "claude_code_cli": "estimated",
        "codex_cli": "estimated",
        "github_copilot": "nominal",
    }
    for runtime, md in matrix.items():
        row = extract_cost_row(md)
        assert row.cost_kind == expected_kind[runtime], (runtime, row)
        assert row.cost_kind != "unknown"


# ---------------------------------------------------------------------------
# F4 — backfill idempotente (claude_code_model -> model en filas históricas)
# ---------------------------------------------------------------------------

def _seed_claude_exec(*, ado_id, model_key="claude_code_model", model_value="claude-sonnet-4-6",
                       has_model=False, runtime="claude_code_cli"):
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="p158", stacky_project_name="p158",
                   title=f"plan158-{ado_id}", ado_state="Active")
        session.add(t)
        session.flush()

        md = {"runtime": runtime, model_key: model_value}
        if has_model:
            md["model"] = model_value
        when = datetime.utcnow()
        e = AgentExecution(
            ticket_id=t.id, agent_type="developer", status="completed",
            input_context_json="[]", started_by="test",
            started_at=when, completed_at=when + timedelta(seconds=5),
            metadata_json=json.dumps(md),
        )
        session.add(e)
        session.flush()
        return e.id


def test_backfill_claude_model_key_copies_from_claude_code_model():
    from services.cost_analytics import backfill_claude_model_key
    from db import session_scope
    from models import AgentExecution

    exec_id = _seed_claude_exec(ado_id=990101)

    result = backfill_claude_model_key()
    assert result["updated"] >= 1

    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        assert row.metadata_dict.get("model") == "claude-sonnet-4-6"


def test_backfill_claude_model_key_is_idempotent():
    from services.cost_analytics import backfill_claude_model_key
    from db import session_scope
    from models import AgentExecution

    exec_id = _seed_claude_exec(ado_id=990102, has_model=True)  # ya tiene "model"

    result = backfill_claude_model_key()
    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        assert row.metadata_dict.get("model") == "claude-sonnet-4-6"

    # correrlo de nuevo no rompe nada ni duplica trabajo sobre filas ya arregladas
    result2 = backfill_claude_model_key()
    assert isinstance(result2["updated"], int)


def test_backfill_claude_model_key_ignores_other_runtimes():
    from services.cost_analytics import backfill_claude_model_key
    from db import session_scope
    from models import AgentExecution

    exec_id = _seed_claude_exec(ado_id=990103, runtime="github_copilot")

    backfill_claude_model_key()
    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        # github_copilot no se toca (ya tiene paridad propia, §2.4)
        assert row.metadata_dict.get("model") is None
