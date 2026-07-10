"""Plan 113 F0 — Flags del Documentador + registro real del agente."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config
from services.harness_flags import FLAG_REGISTRY, categorize

_MASTER = "STACKY_DOCS_DOCUMENTER_ENABLED"
_MAXF = "STACKY_DOCS_DOCUMENTER_MAX_FILES"


def _spec(key):
    return next(s for s in FLAG_REGISTRY if s.key == key)


def test_flags_registered_and_default_off():
    for key in (_MASTER, _MAXF):
        assert categorize(key) == "contexto_memoria", key
    assert config.STACKY_DOCS_DOCUMENTER_ENABLED is False


def test_max_files_bounds_and_requires():
    assert config.STACKY_DOCS_DOCUMENTER_MAX_FILES == 40
    s = _spec(_MAXF)
    assert s.min_value == 1 and s.max_value == 500
    assert s.requires == _MASTER
    assert _spec(_MASTER).requires is None


def test_flags_have_plain_help():
    from services.harness_flags_help import PLAIN_HELP
    for key in (_MASTER, _MAXF):
        assert key in PLAIN_HELP, key


def test_documentador_agent_registered():
    import agents
    assert agents.get("Documentador") is not None


def test_documentador_has_fallback_prompt():
    from services.doc_documenter import _DEFAULT_DOCUMENTADOR_PROMPT
    assert _DEFAULT_DOCUMENTADOR_PROMPT.strip()
    assert "[V]" in _DEFAULT_DOCUMENTADOR_PROMPT
