"""Plan 168 F1 — store de golden tasks (EvalCase) + seeds idempotentes."""
import json

import pytest

import runtime_paths
from evals import case_store, golden_runner


@pytest.fixture
def store_env(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "Developer.agent.md").write_text("# Developer\ncontenido", encoding="utf-8")
    (agents_dir / "BusinessAgent.agent.md").write_text("# Business\ncontenido", encoding="utf-8")
    monkeypatch.setattr(case_store, "prompts_dir", lambda: agents_dir)

    goldens = tmp_path / "goldens"
    (goldens / "developer").mkdir(parents=True)
    (goldens / "developer" / "caso_a.json").write_text(
        json.dumps({
            "name": "caso_a", "agent_type": "developer",
            "output": "trazabilidad ADO-1234 2024-01-01 tests unitarios PASS",
            "expect": {"min_score": 0, "must_pass": True},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(golden_runner, "_AGENTS_DIR", goldens)
    return tmp_path


def test_slug_for_prompt_file():
    assert case_store.slug_for_prompt_file("Developer.agent.md") == "developer"
    assert case_store.slug_for_prompt_file("BusinessAgent.agent.md") == "business"
    assert case_store.slug_for_prompt_file("QAUat1.agent.md") == "qa"
    assert case_store.slug_for_prompt_file("TechnicalAnalyst.v2.agent.md") == "technical"
    assert case_store.slug_for_prompt_file("raro.md") == "raro"


def test_seed_idempotente(store_env):
    first = case_store.ensure_seed_cases()
    ids_first = sorted(c["id"] for c in first)
    assert len(ids_first) == len(set(ids_first)), "ids duplicados en la 1ª corrida"
    second = case_store.ensure_seed_cases()
    ids_second = sorted(c["id"] for c in second)
    assert ids_first == ids_second


def test_seed_shape_artifact(store_env):
    cases = case_store.ensure_seed_cases()
    by_id = {c["id"]: c for c in cases}
    estr = by_id["case-seed-artifact-developer-estructura"]
    assert estr["subject"] == "artifact"
    assert estr["level"] == "deterministic"
    kinds = [c["kind"] for c in estr["checks"]]
    assert kinds == ["min_len", "regex", "max_len"]


def test_seed_golden_ref(store_env):
    cases = case_store.ensure_seed_cases()
    by_id = {c["id"]: c for c in cases}
    golden = by_id["case-seed-golden-developer-caso_a"]
    assert golden["input"]["kind"] == "golden_ref"
    assert golden["input"]["golden_name"] == "caso_a"
    assert golden["input"]["text"] is None  # no copia el output
    assert golden["agent_type"] == "developer"


def test_seed_respeta_ediciones(store_env):
    cases = case_store.ensure_seed_cases()
    target = next(c for c in cases if c["id"] == "case-seed-artifact-developer-rubrica")
    case_store.patch_case(target["id"], weight=3.5)
    cases2 = case_store.ensure_seed_cases()
    edited = next(c for c in cases2 if c["id"] == target["id"])
    assert edited["weight"] == 3.5


def test_create_case_valida_level(store_env):
    with pytest.raises(ValueError) as exc:
        case_store.create_case(
            aspect_key="agent_prompts/developer", subject="artifact",
            level="llm_judge", origin="manual",
            input={"kind": "artifact_text"},
        )
    assert "invalid_case:rubric_id" in str(exc.value)


def test_create_case_valida_check_kind(store_env):
    with pytest.raises(ValueError) as exc:
        case_store.create_case(
            aspect_key="agent_prompts/developer", subject="artifact",
            level="deterministic", origin="manual",
            input={"kind": "artifact_text"},
            checks=[{"kind": "magia"}],
        )
    assert "unknown_check_kind" in str(exc.value)


def test_patch_case_solo_campos_permitidos(store_env):
    case = case_store.create_case(
        aspect_key="agent_prompts/developer", subject="artifact",
        level="deterministic", origin="manual",
        input={"kind": "artifact_text"},
        checks=[{"kind": "min_len", "value": 1}],
    )
    with pytest.raises(ValueError) as exc:
        case_store.patch_case(case["id"], aspect_key="otro")
    assert "invalid_case:campo_no_editable" in str(exc.value)
    updated = case_store.patch_case(case["id"], enabled=False)
    assert updated["enabled"] is False


def test_list_cases_filtros(store_env):
    a = case_store.create_case(
        aspect_key="agent_prompts/developer", subject="artifact",
        level="deterministic", origin="manual", enabled=True,
        input={"kind": "artifact_text"}, checks=[{"kind": "min_len", "value": 1}],
    )
    b = case_store.create_case(
        aspect_key="knowledge_rag", subject="artifact",
        level="deterministic", origin="manual", enabled=False,
        input={"kind": "artifact_text"}, checks=[{"kind": "min_len", "value": 1}],
    )
    only_dev = case_store.list_cases(aspect_key="agent_prompts/developer")
    assert [c["id"] for c in only_dev] == [a["id"]]
    only_enabled_rag = case_store.list_cases(aspect_key="knowledge_rag", enabled=True)
    assert only_enabled_rag == []
    only_disabled_rag = case_store.list_cases(aspect_key="knowledge_rag", enabled=False)
    assert [c["id"] for c in only_disabled_rag] == [b["id"]]


def test_lecturas_tolerantes(store_env):
    path = case_store._cases_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ no es json valido", encoding="utf-8")
    assert case_store.list_cases() == []


def test_golden_ref_exige_agent_type(store_env):
    with pytest.raises(ValueError) as exc:
        case_store.create_case(
            aspect_key="agent_prompts/developer", subject="output",
            level="execution", origin="manual", agent_type=None,
            input={"kind": "golden_ref", "golden_name": "x"},
        )
    assert "invalid_case:agent_type" in str(exc.value)
