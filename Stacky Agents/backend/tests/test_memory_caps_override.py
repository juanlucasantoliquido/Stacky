"""M0.1 — Caps de contexto por agente configurables (STACKY_MEMORY_CAPS_JSON).

Cubre:
  - flag vacío/ausente → _caps_for byte-idéntico a _AGENT_CAPS/_DEFAULT_CAP
  - JSON válido con override parcial → merge sobre defaults (agente ausente intacto)
  - JSON malformado → defaults, sin crash
  - valores inválidos (<=0, shape malo) → ignorados, cae a default de ese agente
  - cache no rompe hot-apply (cambiar el flag se refleja tras invalidar)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _clear_caps_env():
    prev = os.environ.get("STACKY_MEMORY_CAPS_JSON")
    os.environ.pop("STACKY_MEMORY_CAPS_JSON", None)
    from services import memory_store

    memory_store._invalidate_caps_cache()
    yield
    if prev is None:
        os.environ.pop("STACKY_MEMORY_CAPS_JSON", None)
    else:
        os.environ["STACKY_MEMORY_CAPS_JSON"] = prev
    memory_store._invalidate_caps_cache()


def test_empty_flag_is_byte_identical_to_defaults():
    from services import memory_store

    for agent, expected in memory_store._AGENT_CAPS.items():
        assert memory_store._caps_for(agent) == expected
    # agente desconocido → _DEFAULT_CAP
    assert memory_store._caps_for("nope") == memory_store._DEFAULT_CAP
    assert memory_store._caps_for(None) == memory_store._DEFAULT_CAP


def test_valid_override_merges_over_defaults():
    from services import memory_store

    os.environ["STACKY_MEMORY_CAPS_JSON"] = '{"developer": [16, 16000]}'
    memory_store._invalidate_caps_cache()

    assert memory_store._caps_for("developer") == (16, 16000)
    # el resto intacto
    assert memory_store._caps_for("qa") == memory_store._AGENT_CAPS["qa"]
    assert memory_store._caps_for("nope") == memory_store._DEFAULT_CAP


def test_override_can_add_new_agent_and_default():
    from services import memory_store

    os.environ["STACKY_MEMORY_CAPS_JSON"] = '{"custom": [3, 300]}'
    memory_store._invalidate_caps_cache()
    assert memory_store._caps_for("custom") == (3, 300)


def test_malformed_json_falls_back_to_defaults():
    from services import memory_store

    os.environ["STACKY_MEMORY_CAPS_JSON"] = "{not valid json"
    memory_store._invalidate_caps_cache()
    assert memory_store._caps_for("developer") == memory_store._AGENT_CAPS["developer"]


def test_invalid_values_are_ignored_per_agent():
    from services import memory_store

    # developer válido; qa con valor <=0; pm con shape inválido
    os.environ["STACKY_MEMORY_CAPS_JSON"] = (
        '{"developer": [20, 20000], "qa": [0, 8000], "pm": [5], "critic": "x"}'
    )
    memory_store._invalidate_caps_cache()
    assert memory_store._caps_for("developer") == (20, 20000)
    # inválidos caen al default de cada agente
    assert memory_store._caps_for("qa") == memory_store._AGENT_CAPS["qa"]
    assert memory_store._caps_for("pm") == memory_store._AGENT_CAPS["pm"]
    assert memory_store._caps_for("critic") == memory_store._AGENT_CAPS["critic"]


def test_cache_invalidation_reflects_hot_apply():
    from services import memory_store

    os.environ["STACKY_MEMORY_CAPS_JSON"] = '{"developer": [16, 16000]}'
    memory_store._invalidate_caps_cache()
    assert memory_store._caps_for("developer") == (16, 16000)

    os.environ["STACKY_MEMORY_CAPS_JSON"] = '{"developer": [4, 400]}'
    memory_store._invalidate_caps_cache()
    assert memory_store._caps_for("developer") == (4, 400)
