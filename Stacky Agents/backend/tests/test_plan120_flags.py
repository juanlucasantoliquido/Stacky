"""Plan 120 F0 — 5 flags del Centro de Despliegues (default OFF/seguro, requires panel)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from config import config, Config
from services.harness_flags import FLAG_REGISTRY, categorize
from services.harness_flags_help import PLAIN_HELP

_BOOL_KEYS = (
    "STACKY_DEPLOYMENTS_ENABLED",
    "STACKY_DEPLOYMENTS_EXECUTE_ENABLED",
    "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED",
)
_INT_KEYS = (
    "STACKY_DEPLOYMENTS_RETAIN_RELEASES",
    "STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC",
)
_ALL_KEYS = _BOOL_KEYS + _INT_KEYS


def _spec(key):
    return next(s for s in FLAG_REGISTRY if s.key == key)


def _load_devops_health():
    import importlib
    import api.devops as devops_mod
    importlib.reload(devops_mod)
    return devops_mod


def test_flags_known_and_categorized():
    for key in _ALL_KEYS:
        assert categorize(key) == "devops", f"{key} no está en la categoría devops"


def test_defaults_effective_off():
    cfg = Config()
    assert cfg.STACKY_DEPLOYMENTS_ENABLED is False
    assert cfg.STACKY_DEPLOYMENTS_EXECUTE_ENABLED is False
    assert cfg.STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED is False
    assert cfg.STACKY_DEPLOYMENTS_RETAIN_RELEASES == 3
    assert cfg.STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC == 30


def test_flagspec_sin_default_explicito():
    for key in _BOOL_KEYS:
        assert _spec(key).default is None, f"{key} declara default= (gotcha plan 63)"


def test_requires_edges_frozen():
    # La congelación real del mapa la verifica test_harness_flags_requires.py
    # (test_requires_map_is_frozen); acá solo se confirma que la spec declara
    # la arista al master del panel (R4 profundidad 1).
    for key in _ALL_KEYS:
        assert _spec(key).requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_bounds_ints():
    retain = _spec("STACKY_DEPLOYMENTS_RETAIN_RELEASES")
    assert retain.min_value == 1
    assert retain.max_value == 10
    smoke = _spec("STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC")
    assert smoke.min_value == 5
    assert smoke.max_value == 300


def test_harness_defaults_contains_flags():
    env_file = _BACKEND / "harness_defaults.env"
    assert env_file.exists()
    content = env_file.read_text(encoding="utf-8")
    assert "STACKY_DEPLOYMENTS_ENABLED=false" in content
    assert "STACKY_DEPLOYMENTS_EXECUTE_ENABLED=false" in content
    assert "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED=false" in content
    assert "STACKY_DEPLOYMENTS_RETAIN_RELEASES=3" in content
    assert "STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC=30" in content


def test_health_payload_keys_off(monkeypatch):
    devops = _load_devops_health()
    monkeypatch.setattr(config, "STACKY_DEPLOYMENTS_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "STACKY_DEPLOYMENTS_EXECUTE_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED", False, raising=False)
    payload = devops._health_payload()
    assert payload["deployments_enabled"] is False
    assert payload["deployments_execute_enabled"] is False
    assert payload["deployments_ai_enabled"] is False


def test_plainhelp_present():
    for key in _ALL_KEYS:
        assert key in PLAIN_HELP, f"Falta PlainHelp para {key}"
