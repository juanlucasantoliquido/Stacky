"""H0.3 — Tests de _resolve_cwd en claude_code_cli_runner.

Casos:
  1. workspace_root válido (existe) → devuelve el path.
  2. workspace_root seteado pero NO existe → ValueError (nunca fallback silencioso).
  3. workspace_root vacío/None → fallback al dir del repo con warn y metadata flag.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_resolve_cwd_valid_path(tmp_path):
    """workspace_root existente → devuelve (path, False) sin flag de fallback."""
    from services.claude_code_cli_runner import _resolve_cwd

    path, fallback_flag = _resolve_cwd(str(tmp_path))
    assert path == tmp_path
    assert fallback_flag is False


def test_resolve_cwd_invalid_path_raises():
    """workspace_root seteado pero inexistente → ValueError (sin fallback silencioso)."""
    from services.claude_code_cli_runner import _resolve_cwd

    with pytest.raises(ValueError, match="workspace_root"):
        _resolve_cwd("/this/path/absolutely/does/not/exist/xyz_stacky_test")


def test_resolve_cwd_empty_returns_fallback_with_flag():
    """workspace_root vacío/None → fallback al dir del repo, devuelve (path, metadata_flag)."""
    from services.claude_code_cli_runner import _resolve_cwd

    # La función modificada devuelve (Path, cwd_fallback_flag: bool)
    result = _resolve_cwd(None)
    path, fallback_flag = result
    assert isinstance(path, Path)
    assert path.exists()
    assert fallback_flag is True


def test_resolve_cwd_nonempty_returns_no_flag(tmp_path):
    """workspace_root válido → devuelve (path, False) — sin flag de fallback."""
    from services.claude_code_cli_runner import _resolve_cwd

    result = _resolve_cwd(str(tmp_path))
    path, fallback_flag = result
    assert path == tmp_path
    assert fallback_flag is False
