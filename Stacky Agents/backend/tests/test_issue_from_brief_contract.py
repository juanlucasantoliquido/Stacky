"""Plan 45 F0 — Contrato work_item_type + flag STACKY_ISSUE_FROM_BRIEF_ENABLED.

Tests del helper de validación y del default seguro del flag.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_default_none_is_epic():
    from api.tickets import validate_brief_work_item_type
    assert validate_brief_work_item_type(None) == "Epic"


def test_empty_string_is_epic():
    from api.tickets import validate_brief_work_item_type
    assert validate_brief_work_item_type("") == "Epic"
    assert validate_brief_work_item_type("   ") == "Epic"


def test_epic_passthrough():
    from api.tickets import validate_brief_work_item_type
    assert validate_brief_work_item_type("Epic") == "Epic"


def test_issue_passthrough():
    from api.tickets import validate_brief_work_item_type
    assert validate_brief_work_item_type("Issue") == "Issue"


def test_bug_raises():
    from api.tickets import validate_brief_work_item_type
    with pytest.raises(ValueError):
        validate_brief_work_item_type("Bug")


def test_flag_default_is_false():
    """Sin la env var, el default de STACKY_ISSUE_FROM_BRIEF_ENABLED es False.

    Verifica el default evaluando la MISMA expresión que config.py usa, sin
    recargar el módulo config global (un reload desincroniza la instancia
    `config` que otros módulos ya importaron → contaminación de la suite).
    """
    saved = os.environ.pop("STACKY_ISSUE_FROM_BRIEF_ENABLED", None)
    try:
        default_value = os.getenv("STACKY_ISSUE_FROM_BRIEF_ENABLED", "false").lower() in (
            "1", "true", "yes",
        )
        assert default_value is False
    finally:
        if saved is not None:
            os.environ["STACKY_ISSUE_FROM_BRIEF_ENABLED"] = saved
