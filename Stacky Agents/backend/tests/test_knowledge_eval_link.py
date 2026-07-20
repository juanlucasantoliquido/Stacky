"""Plan 170 F4 — migración reservada del 168: origin='lesson' + lección→caso de eval.

KPI-6: `origin='lesson'` en VALID_ORIGINS de case_store y `to-eval-case` crea un caso
borrador (enabled=False, source_ref='lesson:<id>').
"""
import json

import pytest

import runtime_paths
from evals import case_store
from services import knowledge_harvest as kh, knowledge_store as ks


@pytest.fixture
def _env(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return tmp_path


def _seed_active(tmp_path, lesson_id, text, *, title=None, scope=None):
    ev = tmp_path / "evolution"
    ev.mkdir(parents=True, exist_ok=True)
    line = {"lesson_id": lesson_id, "aspect_id": "knowledge_rag", "text": text,
            "origin": "manual", "created_at": "2026-01-01T00:00:00+00:00"}
    with (ev / "lessons.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    ks.upsert_meta(lesson_id, title=title or text[:40], scope=scope)


# 1
def test_valid_origins_incluye_lesson(_env):
    assert "lesson" in case_store.VALID_ORIGINS
    c = case_store.create_case(
        aspect_key="knowledge_rag", agent_type=None, subject="artifact",
        level="deterministic", title="t",
        input={"kind": "artifact_text", "text": None, "golden_name": None},
        checks=[{"kind": "not_contains", "value": "x", "case_sensitive": False}],
        origin="lesson", enabled=False, source_ref="lesson:z",
    )
    assert c["origin"] == "lesson"


# 2
def test_to_eval_case_crea_borrador(_env):
    _seed_active(_env, "prop-a", "no repitas el patrón malo", title="Lección A")
    case = kh.lesson_to_eval_case("prop-a")
    assert case["enabled"] is False
    assert case["origin"] == "lesson"
    assert case["source_ref"] == "lesson:prop-a"
    assert case["checks"][0]["kind"] == "not_contains"
    assert ks.read_meta()["prop-a"]["eval_case_id"] == case["id"]


# 3
def test_to_eval_case_scope_un_agente(_env):
    _seed_active(_env, "dev-1", "regla dev", scope={"agent_types": ["developer"]})
    c1 = kh.lesson_to_eval_case("dev-1")
    assert c1["aspect_key"] == "agent_prompts/developer"
    assert c1["agent_type"] == "developer"
    _seed_active(_env, "glob-1", "regla global", scope={"agent_types": []})
    c2 = kh.lesson_to_eval_case("glob-1")
    assert c2["aspect_key"] == "knowledge_rag"
    assert c2["agent_type"] is None


# 4
def test_to_eval_case_idempotente(_env):
    _seed_active(_env, "prop-b", "otra lección")
    kh.lesson_to_eval_case("prop-b")
    with pytest.raises(ValueError, match="case_already_exists"):
        kh.lesson_to_eval_case("prop-b")


# 5
def test_to_eval_case_retirada_rechaza(_env):
    # meta sin línea activa = retirada
    ks.upsert_meta("retirada", title="Retirada")
    with pytest.raises(ValueError, match="lesson_not_active"):
        kh.lesson_to_eval_case("retirada")
