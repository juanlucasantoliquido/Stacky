"""Plan 117 F1 — núcleo puro de insights (sin DB, sin red)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from services import local_insights as li


def _view(**kw):
    base = {"id": 1, "agent_type": "developer", "status": "completed",
            "error_message": "", "output": "todo ok", "input_context_json": "[]",
            "started_at": None, "completed_at": None, "metadata": {}}
    base.update(kw)
    return base


def test_truncate_middle_short_passthrough():
    assert li.truncate_middle("hola") == "hola"


def test_truncate_middle_long_keeps_head_and_tail():
    text = "A" * 4000 + "Z" * 4000
    out = li.truncate_middle(text)
    assert "[recortado]" in out
    assert out.startswith("A") and out.endswith("Z")


def test_is_eligible_ok():
    assert li.is_eligible(_view())[0] is True


def test_is_eligible_rejects_running():
    assert li.is_eligible(_view(status="running")) == (False, "status_not_terminal")


def test_is_eligible_rejects_cancelled():
    assert li.is_eligible(_view(status="cancelled"))[0] is False


def test_is_eligible_rejects_local_llm_agent_types():
    for at in li.EXCLUDED_AGENT_TYPES:
        assert li.is_eligible(_view(agent_type=at))[0] is False
    assert li.is_eligible(_view(agent_type="local_llm_lo_que_sea"))[0] is False


def test_is_eligible_rejects_backend_local_llm():
    assert li.is_eligible(_view(metadata={"backend": "local_llm"}))[0] is False


def test_should_sweep_skips_existing_insight():
    assert li.should_sweep(_view(metadata={"local_insight": {"state": "done"}})) == (False, "already_has_insight")
    assert li.should_sweep(_view(metadata={"local_insight": {"state": "failed"}}))[0] is False


def test_build_prompt_completed_has_no_error_section():
    _, user = li.build_insight_prompt(_view(status="completed"))
    assert "== ERROR ==" not in user
    assert "null en probable_cause" in user


def test_build_prompt_error_includes_error_message():
    _, user = li.build_insight_prompt(_view(status="error", error_message="boom xyz"))
    assert "== ERROR ==" in user and "boom xyz" in user


def test_parse_valid_json():
    out = li.parse_insight_response('{"tldr":"ok","labels":["a"],"risk":"high","probable_cause":null,"evidence":null,"next_step":null}')
    assert out["tldr"] == "ok" and out["risk"] == "high" and out["labels"] == ["a"]


def test_parse_strips_fences():
    out = li.parse_insight_response('```json\n{"tldr":"x"}\n```')
    assert out["tldr"] == "x"


def test_parse_invalid_json_raises():
    with pytest.raises(ValueError):
        li.parse_insight_response("no soy json")


def test_parse_missing_tldr_raises():
    with pytest.raises(ValueError):
        li.parse_insight_response('{"labels":["a"]}')


def test_parse_caps_labels_and_lengths():
    labels = [("x" * 100) for _ in range(7)]
    out = li.parse_insight_response('{"tldr":"t","labels":' + str(labels).replace("'", '"') + '}')
    assert len(out["labels"]) == 5
    assert all(len(l) <= 40 for l in out["labels"])


def test_parse_bad_risk_defaults_low():
    out = li.parse_insight_response('{"tldr":"t","risk":"catastrofico"}')
    assert out["risk"] == "low"


def test_make_insight_metadata_contract():
    md = li.make_insight_metadata({"tldr": "t", "labels": [], "risk": "low",
                                   "probable_cause": None, "evidence": None, "next_step": None},
                                  model="qwen", attempts=1)
    assert md["state"] == "done" and md["model"] == "qwen" and md["attempts"] == 1
    assert md["generated_at"].endswith("Z")
