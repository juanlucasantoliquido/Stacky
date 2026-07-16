"""Plan 146 — Fixes verificados de bajo esfuerzo (V1, V5, V4).

Un solo archivo con los tests de contrato/comportamiento de las 3 correcciones.
Correr aislado:  .venv/Scripts/python.exe -m pytest tests/test_plan146_verified_fixes.py -q
"""
from __future__ import annotations

import logging
import json as _json
from contextlib import contextmanager

import pytest


def test_plan146_scaffold():
    """Placeholder para que el archivo exista y el ratchet lo clasifique (F0)."""
    assert True


# ---------- V1: import real de AgentExecution + session_scope ----------

def test_sweep_recent_runs_real_import_path_no_import_error(monkeypatch, caplog):
    """V1: con _db_runs=None se ejecuta el IMPORT REAL del módulo models/db.

    Antes del fix, 'from models import Execution, session_scope' lanzaba
    ImportError ('cannot import name Execution') capturado y logueado como
    'sweep_recent_runs: error general'. El import NO se mockea: solo se
    inyecta una sesión falsa vía monkeypatch de db.session_scope para no
    tocar la DB real.
    """
    import db as db_mod

    class _FakeQuery:
        def order_by(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def all(self):
            return []

    class _FakeSession:
        def query(self, *a, **k):
            return _FakeQuery()

    @contextmanager
    def _fake_scope():
        yield _FakeSession()

    # El fix hace 'from db import session_scope' DENTRO de la función:
    # parchear db.session_scope basta (se resuelve en tiempo de llamada).
    monkeypatch.setattr(db_mod, "session_scope", _fake_scope)

    from services.ado_edit_learning import sweep_recent_runs

    with caplog.at_level(logging.WARNING):
        result = sweep_recent_runs(_db_runs=None, _learn_fn=lambda **k: None)

    assert result == 0
    assert "cannot import name" not in caplog.text
    assert "error general" not in caplog.text


def test_sweep_reads_metadata_json_from_real_shaped_run(monkeypatch):
    """V1 (2º bug) + C2/C4: un run 'real' refleja EXACTAMENTE la forma de
    AgentExecution (models.py:207): expone la columna `.metadata_json` (str JSON),
    la property canónica `.metadata_dict` (dict parseado) y `.metadata` = el
    registro MetaData de SQLAlchemy (NO dict). El sweep debe leer el dict correcto
    (vía `metadata_dict` canónico) y extraer epic_ado_id — nunca el objeto MetaData.
    """
    from services.ado_edit_learning import sweep_recent_runs, LearnResult

    class _RealShapedRun:
        id = 7
        metadata_json = _json.dumps({"epic_ado_id": 999, "project_name": "P"})
        metadata = object()  # NO es dict: emula MetaData de SQLAlchemy

        @property
        def metadata_dict(self) -> dict:
            # Espejo fiel de AgentExecution.metadata_dict (models.py:259-261).
            return _json.loads(self.metadata_json)

    seen = {}

    def fake_learn(**kw):
        seen.update(kw)
        return LearnResult(
            learned=True, lesson_written=True, golden_written=False,
            rev=2, reason="ok",
        )

    result = sweep_recent_runs(
        _db_runs=[_RealShapedRun()],
        _ado_client_factory=lambda p: object(),
        _learn_fn=fake_learn,
    )

    assert seen.get("ado_id") == 999
    assert result == 1


# ---------- V5: mkdir del SQLite ledger + dedup del warning ----------

def test_ledger_creates_parent_dir_when_missing(monkeypatch, tmp_path):
    """V5: si el directorio padre de la DB no existe, el ledger lo crea y
    persiste en SQLite (el archivo .db queda en disco). Antes del fix,
    sqlite3.connect fallaba con 'unable to open database file' y NO se creaba
    el archivo (caía a JSONL)."""
    import services.ado_edit_ledger as lm

    nested_db = tmp_path / "no" / "existe" / "aun" / "ledger.db"
    monkeypatch.setattr(lm, "_get_db_path", lambda: str(nested_db))
    monkeypatch.setattr(lm, "_get_jsonl_path", lambda: tmp_path / "ledger.jsonl")
    monkeypatch.setattr(lm, "_SQLITE_WARN_STATE", {})

    lm.mark_learned(111, 3, "run-x")

    assert nested_db.exists(), "el fix debe crear el dir padre y la DB SQLite"
    assert lm.already_learned(111, 3) is True


def test_ledger_warns_once_per_signature_when_sqlite_unavailable(monkeypatch, tmp_path, caplog):
    """V5: ante el MISMO fallo repetido, se emite UNA sola advertencia (dedup por
    firma). El resto degrada silencioso a JSONL. Todas las operaciones lanzan la
    misma OperationalError → una firma → un warning."""
    import sqlite3
    import services.ado_edit_ledger as lm

    monkeypatch.setattr(lm, "_get_jsonl_path", lambda: tmp_path / "ledger.jsonl")
    monkeypatch.setattr(lm, "_SQLITE_WARN_STATE", {})

    def _boom(*a, **k):
        raise sqlite3.OperationalError("unable to open database file")

    # _connect es el único punto de apertura tras el fix.
    monkeypatch.setattr(lm, "_connect", _boom)

    with caplog.at_level(logging.WARNING):
        lm.mark_learned(1, 1, "r1")
        lm.mark_learned(2, 2, "r2")
        lm.already_learned(3, 3)

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "SQLite no disponible" in r.getMessage()
    ]
    assert len(warnings) == 1, f"esperaba 1 warning dedup por firma, hubo {len(warnings)}"


def test_ledger_rewarns_on_distinct_sqlite_failure(monkeypatch, tmp_path, caplog):
    """C3: un fallo con firma DISTINTA vuelve a advertir. Un booleano global de un
    solo disparo lo habría silenciado para siempre; el dedup por firma NO oculta un
    fallo nuevo/persistente."""
    import sqlite3
    import services.ado_edit_ledger as lm

    monkeypatch.setattr(lm, "_get_jsonl_path", lambda: tmp_path / "ledger.jsonl")
    monkeypatch.setattr(lm, "_SQLITE_WARN_STATE", {})
    # No consumir el iterador con _create_table_if_needed intermedio:
    monkeypatch.setattr(lm, "_create_table_if_needed", lambda: None)

    errs = iter([
        sqlite3.OperationalError("unable to open database file"),
        sqlite3.OperationalError("database disk image is malformed"),  # firma distinta
    ])

    def _boom_seq(*a, **k):
        raise next(errs)

    monkeypatch.setattr(lm, "_connect", _boom_seq)

    with caplog.at_level(logging.WARNING):
        lm.already_learned(1, 1)   # 1ª firma → warning
        lm.already_learned(2, 2)   # 2ª firma distinta → warning

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "SQLite no disponible" in r.getMessage()
    ]
    assert len(warnings) == 2, f"cada firma distinta debe advertir una vez, hubo {len(warnings)}"


# ---------- V4: contrato de atributos de Config que el runner de Claude lee ----------

# Atributos que services/claude_code_cli_runner.py lee de `config`.
# Si una regresión de config.py borra cualquiera, el runner crashea en runtime
# ('Config' object has no attribute ...). Este contrato lo bloquea en CI.
_CLAUDE_RUNNER_CONFIG_ATTRS = [
    "CLAUDE_CODE_CLI_MODEL",
    "CLAUDE_CODE_CLI_MODEL_FALLBACK",   # V4: el que faltaba en deploy v1.0.76
    "CLAUDE_CODE_CLI_BIN",
    "CLAUDE_CODE_CLI_TIMEOUT",
    "CLAUDE_CODE_CLI_EFFORT",
    "CLAUDE_CODE_CLI_SKIP_PERMISSIONS",
    "CLAUDE_CODE_CLI_PERMISSION_MODE",
    "CLAUDE_CODE_CLI_SYSTEM_PROMPT_MODE",
    "CLAUDE_CODE_CLI_HOOKS_ENABLED",
    "CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED",
    "CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES",
    "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED",
]


@pytest.mark.parametrize("attr", _CLAUDE_RUNNER_CONFIG_ATTRS)
def test_config_exposes_claude_runner_attribute(attr):
    """V4: la instancia `config` expone cada atributo crítico del runner de Claude."""
    from config import config
    assert hasattr(config, attr), (
        f"Config no expone {attr}: el runner de Claude crasheará en runtime. "
        f"Regresión de config.py (ver Plan 146 / hallazgo V4)."
    )


def test_config_model_fallback_is_nonempty_str():
    """V4: el fallback tiene un default usable (no None/vacío)."""
    from config import config
    val = config.CLAUDE_CODE_CLI_MODEL_FALLBACK
    assert isinstance(val, str) and val.strip(), "fallback debe ser un modelo no vacío"
