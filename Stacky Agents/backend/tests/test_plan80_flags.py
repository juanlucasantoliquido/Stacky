"""Plan 80 F0 — Flags codebase-memory-mcp *_PROJECTS / *_BINARY_PATH +
fix _type_zero("str") + fix _cast branch "str" (pre-requisito bloqueante).

Casos:
  1. config.STACKY_CODEBASE_MEMORY_MCP_PROJECTS == "" por default.
  2. config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH == "" por default.
  3. codebase_memory_mcp_enabled -> False con master OFF.
  4. codebase_memory_mcp_enabled -> True con master ON + allowlist vacía.
  5. codebase_memory_mcp_enabled -> True solo si el proyecto está en la allowlist.
  6. FLAG_REGISTRY contiene *_PROJECTS con env_only=False, type=csv, pair, categorizada.
  7. FLAG_REGISTRY contiene *_BINARY_PATH con env_only=False, type=str, categorizada.
  8. _type_zero("str") == "" (no 0 int).
  9. _type_zero regresión bool/csv/float/int.
  10. _cast para "str" no lanza (BUG BLOQUEANTE).
  11. _cast para "str" con None -> "".
  12. _cast regresión sobre STACKY_MIGRATOR_EPIC_POLICY (type=str, Plan 74).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_config_projects_default_empty():
    from config import config

    assert config.STACKY_CODEBASE_MEMORY_MCP_PROJECTS == ""


def test_config_binary_path_default_empty():
    from config import config

    assert config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH == ""


def test_codebase_memory_mcp_enabled_master_off():
    from services.cli_feature_flags import codebase_memory_mcp_enabled

    with patch("config.config.STACKY_CODEBASE_MEMORY_MCP_ENABLED", False), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_PROJECTS", ""):
        assert codebase_memory_mcp_enabled("X") is False


def test_codebase_memory_mcp_enabled_master_on_empty_allowlist():
    from services.cli_feature_flags import codebase_memory_mcp_enabled

    with patch("config.config.STACKY_CODEBASE_MEMORY_MCP_ENABLED", True), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_PROJECTS", ""):
        assert codebase_memory_mcp_enabled("X") is True


def test_codebase_memory_mcp_enabled_allowlist_filters():
    from services.cli_feature_flags import codebase_memory_mcp_enabled

    with patch("config.config.STACKY_CODEBASE_MEMORY_MCP_ENABLED", True), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_PROJECTS", "X"):
        assert codebase_memory_mcp_enabled("X") is True
        assert codebase_memory_mcp_enabled("Y") is False


def test_flag_registry_has_projects_spec():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

    by_key = {s.key: s for s in FLAG_REGISTRY}
    spec = by_key["STACKY_CODEBASE_MEMORY_MCP_PROJECTS"]
    assert spec.env_only is False
    assert spec.type == "csv"
    assert spec.pair == "STACKY_CODEBASE_MEMORY_MCP_ENABLED"
    assert spec.key in _CATEGORY_KEYS["avanzado"]


def test_flag_registry_has_binary_path_spec():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

    by_key = {s.key: s for s in FLAG_REGISTRY}
    spec = by_key["STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH"]
    assert spec.env_only is False
    assert spec.type == "str"
    assert spec.key in _CATEGORY_KEYS["avanzado"]


def test_type_zero_str_is_empty_string():
    from services.harness_flags import _type_zero

    assert _type_zero("str") == ""
    assert isinstance(_type_zero("str"), str)


def test_type_zero_regression_other_types():
    from services.harness_flags import _type_zero

    assert _type_zero("bool") is False
    assert _type_zero("csv") == ""
    assert _type_zero("float") == 0.0
    assert _type_zero("int") == 0


def test_cast_str_does_not_raise():
    from services.harness_flags import FLAG_REGISTRY, _cast

    by_key = {s.key: s for s in FLAG_REGISTRY}
    spec_str = by_key["STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH"]
    assert _cast(spec_str, "C:\\tools\\cbm.exe") == "C:\\tools\\cbm.exe"


def test_cast_str_none_returns_empty():
    from services.harness_flags import FLAG_REGISTRY, _cast

    by_key = {s.key: s for s in FLAG_REGISTRY}
    spec_str = by_key["STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH"]
    assert _cast(spec_str, None) == ""


def test_cast_str_regression_migrator_epic_policy():
    from services.harness_flags import FLAG_REGISTRY, _cast

    by_key = {s.key: s for s in FLAG_REGISTRY}
    spec_migrator = by_key["STACKY_MIGRATOR_EPIC_POLICY"]
    assert _cast(spec_migrator, "free_degrade") == "free_degrade"
