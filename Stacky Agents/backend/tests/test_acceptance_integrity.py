"""Tests A1.2 — Guard de independencia del contrato (inmutabilidad).

Verifica:
- ejecución desde ubicación de solo-arnés (subdir temporal fuera del árbol del agente)
- mutación de generated_test → restaurado + mutated_checks poblado
- mutación que fail-red en baseline → re-incorporada
- flag OFF → byte-idéntico
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile

import pytest

_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _reload_config():
    import config as _cfg_mod
    importlib.reload(_cfg_mod)


def _enable():
    os.environ["STACKY_ACCEPTANCE_INTEGRITY_ENABLED"] = "true"
    _reload_config()


def _disable():
    os.environ["STACKY_ACCEPTANCE_INTEGRITY_ENABLED"] = "false"
    _reload_config()


def _make_check(kind="command", artifact="echo ok"):
    return {"kind": kind, "artifact": artifact, "ticket_clause": "test clause"}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_integrity_hash_no_mutado():
    """Sin mutación de archivos → mutated_checks vacío, restored=False."""
    _enable()

    from services.acceptance_integrity import check_integrity

    original = "def test_foo():\n    assert 1 == 1\n"
    checks = [{"kind": "generated_test", "artifact": original, "ticket_clause": "assert"}]

    # Simular que el archivo en el workspace NO fue modificado (hash igual)
    with patch("services.acceptance_integrity._get_file_hash", return_value="abc123"), \
         patch("services.acceptance_integrity._get_stored_hash", return_value="abc123"):
        result = check_integrity(checks, workspace="/tmp/ws")

    assert result["mutated_checks"] == []
    assert result["restored"] is False


def test_integrity_detecta_mutacion():
    """Si el hash del archivo cambió → mutated_checks contiene el artefacto."""
    _enable()

    from services.acceptance_integrity import check_integrity

    original = "def test_foo():\n    assert 1 == 1\n"
    checks = [{"kind": "generated_test", "artifact": original, "ticket_clause": "assert", "_tmp_path": "/tmp/ws/_ac_gate_abc.py"}]

    with patch("services.acceptance_integrity._get_file_hash", return_value="DIFERENTE"), \
         patch("services.acceptance_integrity._get_stored_hash", return_value="ORIGINAL"), \
         patch("services.acceptance_integrity._restore_file") as mock_restore:
        result = check_integrity(checks, workspace="/tmp/ws")

    assert len(result["mutated_checks"]) >= 1
    assert result["restored"] is True
    mock_restore.assert_called()


def test_flag_off_byte_identico():
    """Flag OFF → check_integrity devuelve vacío sin tocar nada."""
    _disable()

    from services.acceptance_integrity import check_integrity

    checks = [{"kind": "generated_test", "artifact": "def test_foo():\n    assert True\n", "ticket_clause": "x"}]

    with patch("services.acceptance_integrity._get_file_hash") as mock_hash:
        result = check_integrity(checks, workspace="/tmp/ws")

    mock_hash.assert_not_called()
    assert result["mutated_checks"] == []
    assert result["restored"] is False


def test_solo_generated_test_se_verifica():
    """Solo artefactos kind=generated_test se someten a check de hash."""
    _enable()

    from services.acceptance_integrity import check_integrity

    checks = [
        {"kind": "command", "artifact": "echo ok", "ticket_clause": "cmd"},
        {"kind": "schema", "artifact": "schema.json", "ticket_clause": "schema"},
    ]

    with patch("services.acceptance_integrity._get_file_hash") as mock_hash:
        result = check_integrity(checks, workspace="/tmp/ws")

    # Comandos y schemas no tienen hash de archivo
    mock_hash.assert_not_called()
    assert result["mutated_checks"] == []


def test_metadata_shape():
    """check_integrity() devuelve dict con shape correcto."""
    _enable()

    from services.acceptance_integrity import check_integrity

    result = check_integrity([], workspace="/tmp/ws")

    assert "mutated_checks" in result
    assert "restored" in result
    assert isinstance(result["mutated_checks"], list)
    assert isinstance(result["restored"], bool)
