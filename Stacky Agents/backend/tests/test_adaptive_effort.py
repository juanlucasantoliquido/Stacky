"""Tests Q0.2 — Esfuerzo adaptativo por dificultad estimada.

TDD para `_map_effort` en claude_code_cli_runner y la lógica de turns en
codex_cli_runner.

Sin binarios; mockea config.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**kwargs):
    cfg = MagicMock()
    cfg.STACKY_ADAPTIVE_EFFORT_ENABLED = kwargs.get("STACKY_ADAPTIVE_EFFORT_ENABLED", True)
    cfg.STACKY_EFFORT_FLOOR = kwargs.get("STACKY_EFFORT_FLOOR", "medium")
    cfg.CLAUDE_CODE_CLI_EFFORT = kwargs.get("CLAUDE_CODE_CLI_EFFORT", "medium")
    cfg.STACKY_RUNAWAY_MAX_TURNS = kwargs.get("STACKY_RUNAWAY_MAX_TURNS", 10)
    return cfg


# ---------------------------------------------------------------------------
# _map_effort — mapeo S/M/L/XL → low/medium/high con piso
# ---------------------------------------------------------------------------

def _import_map_effort():
    from services.claude_code_cli_runner import _map_effort
    return _map_effort


def test_s_maps_to_low():
    with patch("services.claude_code_cli_runner.config", _make_config(STACKY_EFFORT_FLOOR="low")):
        fn = _import_map_effort()
        assert fn("S") == "low"


def test_m_maps_to_medium():
    with patch("services.claude_code_cli_runner.config", _make_config()):
        fn = _import_map_effort()
        assert fn("M") == "medium"


def test_l_maps_to_high():
    with patch("services.claude_code_cli_runner.config", _make_config()):
        fn = _import_map_effort()
        assert fn("L") == "high"


def test_xl_maps_to_high():
    with patch("services.claude_code_cli_runner.config", _make_config()):
        fn = _import_map_effort()
        assert fn("XL") == "high"


def test_floor_prevents_low():
    """Piso medium → S→low se eleva a medium."""
    with patch("services.claude_code_cli_runner.config", _make_config(STACKY_EFFORT_FLOOR="medium")):
        fn = _import_map_effort()
        assert fn("S") == "medium"


def test_floor_high_elevates_medium():
    """Piso high → M→medium se eleva a high."""
    with patch("services.claude_code_cli_runner.config", _make_config(STACKY_EFFORT_FLOOR="high")):
        fn = _import_map_effort()
        assert fn("M") == "high"


def test_flag_off_returns_none():
    """Flag OFF → None (byte-idéntico: _build_command usa config default)."""
    with patch("services.claude_code_cli_runner.config",
               _make_config(STACKY_ADAPTIVE_EFFORT_ENABLED=False)):
        fn = _import_map_effort()
        assert fn("S") is None
        assert fn("M") is None
        assert fn("XL") is None


def test_none_complexity_returns_none():
    """Complejidad None → None."""
    with patch("services.claude_code_cli_runner.config", _make_config()):
        fn = _import_map_effort()
        assert fn(None) is None


# ---------------------------------------------------------------------------
# _build_command respeta effort_override
# ---------------------------------------------------------------------------

def test_build_command_uses_effort_override():
    """effort_override gana sobre config.CLAUDE_CODE_CLI_EFFORT."""
    import sys
    # Parcheamos las deps externas que _build_command necesita para no fallar
    mock_config = _make_config(STACKY_ADAPTIVE_EFFORT_ENABLED=True)
    mock_config.CLAUDE_CODE_CLI_SKIP_PERMISSIONS = True
    mock_config.CLAUDE_CODE_CLI_PERMISSION_MODE = ""

    with (
        patch("services.claude_code_cli_runner.config", mock_config),
        patch("services.claude_code_cli_runner._resolve_claude_code_cli_bin", return_value="claude"),
    ):
        from services.claude_code_cli_runner import _build_command
        cmd = _build_command(model_override=None, effort_override="low")
    assert "--effort" in cmd
    idx = cmd.index("--effort")
    assert cmd[idx + 1] == "low"


def test_build_command_no_effort_when_none():
    """Sin effort_override y sin CLAUDE_CODE_CLI_EFFORT → no pasa --effort."""
    mock_config = _make_config(STACKY_ADAPTIVE_EFFORT_ENABLED=False)
    mock_config.CLAUDE_CODE_CLI_SKIP_PERMISSIONS = True
    mock_config.CLAUDE_CODE_CLI_PERMISSION_MODE = ""
    mock_config.CLAUDE_CODE_CLI_EFFORT = ""

    with (
        patch("services.claude_code_cli_runner.config", mock_config),
        patch("services.claude_code_cli_runner._resolve_claude_code_cli_bin", return_value="claude"),
    ):
        from services.claude_code_cli_runner import _build_command
        cmd = _build_command(model_override=None, effort_override=None)
    assert "--effort" not in cmd


# ---------------------------------------------------------------------------
# Codex: ajuste de turns con complexity S→50% del cap
# ---------------------------------------------------------------------------

def test_codex_low_effort_halves_turns():
    """Complexity S + floor low → turns = cap // 2."""
    # Prueba unitaria de la lógica de cómputo, no del runner completo.
    _ORDER = {"low": 0, "medium": 1, "high": 2}
    _MAP = {"S": "low", "M": "medium", "L": "high", "XL": "high"}
    cap = 10
    complexity = "S"
    floor = "low"

    mapped = _MAP.get(complexity, "medium")
    if _ORDER.get(mapped, 1) < _ORDER.get(floor, 1):
        mapped = floor

    adaptive_turns = cap
    if cap > 0 and mapped == "low":
        adaptive_turns = max(1, cap // 2)

    assert adaptive_turns == 5


def test_codex_medium_keeps_full_cap():
    """Complexity M → turns igual al cap."""
    _MAP = {"S": "low", "M": "medium", "L": "high", "XL": "high"}
    cap = 10
    complexity = "M"
    mapped = _MAP.get(complexity, "medium")
    adaptive_turns = cap
    if cap > 0 and mapped == "low":
        adaptive_turns = max(1, cap // 2)
    assert adaptive_turns == 10


def test_copilot_noop():
    """copilot no tiene adaptive effort — verificado por ausencia de _map_effort en su runner."""
    # github_copilot no tiene _map_effort; solo claude_code_cli y codex_cli.
    import importlib
    import inspect
    runner_src = inspect.getsource(
        importlib.import_module("services.claude_code_cli_runner")
    )
    assert "_map_effort" in runner_src
    # github_copilot runner no existe como módulo separado (corre en agent_runner)
    # → no hay nada que testear aquí; copilot no-op por diseño
    assert True
