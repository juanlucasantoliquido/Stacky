"""tests/test_plan94_variables_pure.py — Plan 94 F1.
Tests de helpers PUROS validate_variable_key y looks_secret."""
import json
from pathlib import Path

import pytest

from services.ci_variables import looks_secret, validate_variable_key


def _fixture_path() -> Path:
    return Path(__file__).parent / "fixtures" / "plan94_secret_hints.json"


def test_f1_key_valid_and_invalid():
    """Validación de keys: válidas e inválidas."""
    # Válidas
    assert validate_variable_key("DEPLOY_PATH") is None
    assert validate_variable_key("_x") is None
    assert validate_variable_key("A") is None

    # Inválidas
    assert validate_variable_key("") == "La key no puede estar vacía"
    assert validate_variable_key("9X")  # empieza con número
    assert validate_variable_key("con espacios")  # espacios no permitidos
    assert validate_variable_key("a-b")  # guion no permitido
    long_key = "x" * 256
    assert "excede" in validate_variable_key(long_key)


def test_f1_secret_hints_shared_fixture():
    """Paridad backend/frontend por fixture compartido (16 casos)."""
    fixture = json.loads(_fixture_path().read_text(encoding="utf-8"))

    # Los que deben matchear (secret → True)
    for key in fixture["secret"]:
        assert looks_secret(key) is True, f"{key} debería parecer secreto"

    # Los que NO deben matchear (not_secret → False)
    for key in fixture["not_secret"]:
        assert looks_secret(key) is False, f"{key} NO debería parecer secreto"


def test_f1_pure_no_io():
    """C9: el módulo ci_variables.py NO debe importar Flask/requests (puro)."""
    source = Path(__file__).parent.parent / "services" / "ci_variables.py"
    content = source.read_text(encoding="utf-8")

    # Estos imports NO deben aparecer (harían I/O posible)
    assert "import flask" not in content
    assert "from flask" not in content
    assert "import requests" not in content
    assert "from requests" not in content
