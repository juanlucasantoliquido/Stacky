"""Unit tests for intent_inferrer.py — Fase 7 Intent Inference.

Coverage:
- _match_label() correct classification: exact, normalised, unknown, empty.
- _build_vocabulary() returns a non-empty sorted list from navigation_graph.
- _build_system_prompt() includes vocabulary labels.
- _build_user_prompt() includes the navigation path.
- infer_goal_from_path() returns InferResult with ok=True for known labels.
- infer_goal_from_path() handles "unknown" LLM response gracefully.
- infer_goal_from_path() handles LLM error gracefully (ok=False).
- infer_goal_from_path() rejects paths that are too short.
- infer_from_session_file() reads navigation_path from session.json.
- infer_from_session_file() returns ok=False for missing file.
- InferResult.to_dict() contains all documented fields.
- intent_parser v1.2.0 sets goal_action when inferrer returns a label.
- intent_parser does NOT override an existing goal_action with inference.
- session_recorder._build_session_payload includes inferred_goal_action field.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")


# ── _match_label() ────────────────────────────────────────────────────────────

def test_match_label_exact_returns_high():
    import intent_inferrer as ii
    vocab = ["buscar_cliente", "crear_compromiso_pago"]
    goal, conf = ii._match_label("buscar_cliente", vocab)
    assert goal == "buscar_cliente"
    assert conf == "high"


def test_match_label_case_insensitive_returns_low():
    import intent_inferrer as ii
    vocab = ["buscar_cliente", "crear_compromiso_pago"]
    goal, conf = ii._match_label("Buscar_Cliente", vocab)
    assert goal == "buscar_cliente"
    assert conf == "low"


def test_match_label_spaces_normalised_to_underscores():
    import intent_inferrer as ii
    vocab = ["crear_compromiso_pago"]
    goal, conf = ii._match_label("crear compromiso pago", vocab)
    assert goal == "crear_compromiso_pago"
    assert conf == "low"


def test_match_label_unknown_literal_returns_empty():
    import intent_inferrer as ii
    vocab = ["buscar_cliente"]
    goal, conf = ii._match_label("unknown", vocab)
    assert goal == ""
    assert conf == "unknown"


def test_match_label_empty_string_returns_unknown():
    import intent_inferrer as ii
    goal, conf = ii._match_label("", [])
    assert goal == ""
    assert conf == "unknown"


def test_match_label_no_match_returns_unknown():
    import intent_inferrer as ii
    vocab = ["buscar_cliente", "crear_nota"]
    goal, conf = ii._match_label("hacer_algo_totalmente_desconocido", vocab)
    assert goal == ""
    assert conf == "unknown"


def test_match_label_strips_punctuation():
    import intent_inferrer as ii
    vocab = ["buscar_cliente"]
    goal, conf = ii._match_label('"buscar_cliente".', vocab)
    assert goal == "buscar_cliente"
    assert conf == "high"


def test_match_label_prefix_match_returns_low():
    """LLM sometimes returns the label with trailing explanation."""
    import intent_inferrer as ii
    vocab = ["buscar_cliente"]
    # Model wrote the label then added garbage
    goal, conf = ii._match_label("buscar_cliente_extended", vocab)
    # buscar_cliente_extended starts with buscar_cliente → low
    assert goal == "buscar_cliente"
    assert conf == "low"


# ── _build_vocabulary() ───────────────────────────────────────────────────────

def test_build_vocabulary_returns_known_labels():
    import intent_inferrer as ii
    vocab = ii._build_vocabulary()
    assert isinstance(vocab, list)
    assert len(vocab) > 5
    assert "buscar_cliente" in vocab
    assert "crear_compromiso_pago" in vocab


def test_build_vocabulary_is_sorted():
    import intent_inferrer as ii
    vocab = ii._build_vocabulary()
    assert vocab == sorted(vocab)


def test_build_vocabulary_no_duplicates():
    import intent_inferrer as ii
    vocab = ii._build_vocabulary()
    assert len(vocab) == len(set(vocab))


# ── _build_system_prompt() / _build_user_prompt() ────────────────────────────

def test_system_prompt_contains_vocabulary_labels():
    import intent_inferrer as ii
    vocab = ["buscar_cliente", "crear_compromiso_pago"]
    prompt = ii._build_system_prompt(vocab)
    assert "buscar_cliente" in prompt
    assert "crear_compromiso_pago" in prompt


def test_user_prompt_contains_path_screens():
    import intent_inferrer as ii
    path = ["FrmLogin.aspx", "FrmBusqueda.aspx", "FrmDetalleClie.aspx"]
    prompt = ii._build_user_prompt(path)
    assert "FrmLogin.aspx" in prompt
    assert "FrmDetalleClie.aspx" in prompt


def test_user_prompt_uses_arrow_separator():
    import intent_inferrer as ii
    path = ["FrmLogin.aspx", "FrmBusqueda.aspx"]
    prompt = ii._build_user_prompt(path)
    assert "→" in prompt


# ── InferResult.to_dict() ─────────────────────────────────────────────────────

def test_infer_result_to_dict_has_all_fields():
    import intent_inferrer as ii
    r = ii.InferResult(
        ok=True,
        goal_action="buscar_cliente",
        confidence="high",
        raw_response="buscar_cliente",
        model="gpt-4.1-mini",
        duration_ms=42,
    )
    d = r.to_dict()
    for field in ("ok", "goal_action", "confidence", "raw_response", "model", "duration_ms", "error"):
        assert field in d, f"Missing field: {field}"


def test_infer_result_default_error_is_empty():
    import intent_inferrer as ii
    r = ii.InferResult(ok=True, goal_action="", confidence="unknown",
                       raw_response="", model="", duration_ms=0)
    assert r.error == ""


# ── infer_goal_from_path() with monkeypatched LLM ────────────────────────────

def test_infer_goal_known_label_exact(monkeypatch):
    """When LLM returns an exact label, result should be high confidence."""
    import intent_inferrer as ii
    monkeypatch.setattr(ii, "call_llm" if hasattr(ii, "call_llm") else "_dummy",
                        None, raising=False)

    # Monkeypatch call_llm at module level inside the function call
    import llm_client
    monkeypatch.setattr(
        llm_client, "call_llm",
        lambda **kwargs: {"text": "crear_compromiso_pago", "model": "mock", "duration_ms": 5},
    )
    # Re-import to pick up monkeypatched call_llm
    result = ii.infer_goal_from_path(
        ["FrmLogin.aspx", "FrmDetalleClie.aspx", "PopUpCompromisos.aspx"]
    )
    assert result.ok
    assert result.goal_action == "crear_compromiso_pago"
    assert result.confidence == "high"


def test_infer_goal_unknown_response(monkeypatch):
    """When LLM returns 'unknown', result is ok=True but goal_action is empty."""
    import intent_inferrer as ii
    import llm_client
    monkeypatch.setattr(
        llm_client, "call_llm",
        lambda **kwargs: {"text": "unknown", "model": "mock", "duration_ms": 5},
    )
    result = ii.infer_goal_from_path(
        ["FrmLogin.aspx", "FrmBusqueda.aspx"]
    )
    assert result.ok
    assert result.goal_action == ""
    assert result.confidence == "unknown"


def test_infer_goal_llm_error(monkeypatch):
    """When LLM raises an exception, result is ok=False with error populated."""
    import intent_inferrer as ii
    import llm_client
    monkeypatch.setattr(
        llm_client, "call_llm",
        lambda **kwargs: (_ for _ in ()).throw(llm_client.LLMError("connection refused")),
    )
    result = ii.infer_goal_from_path(
        ["FrmLogin.aspx", "FrmBusqueda.aspx"]
    )
    assert not result.ok
    assert "connection refused" in result.error


def test_infer_goal_path_too_short():
    """A path with fewer than _MIN_PATH_LENGTH unique screens returns unknown."""
    import intent_inferrer as ii
    result = ii.infer_goal_from_path(["FrmLogin.aspx"])
    assert result.ok  # soft failure, not hard
    assert result.goal_action == ""
    assert result.confidence == "unknown"
    assert "too short" in result.error.lower()


def test_infer_goal_empty_path():
    import intent_inferrer as ii
    result = ii.infer_goal_from_path([])
    assert result.ok
    assert result.goal_action == ""


def test_infer_goal_deduplicates_path(monkeypatch):
    """Repeated screens are deduplicated before inferring."""
    import intent_inferrer as ii
    import llm_client

    captured: list[str] = []

    def _capture(**kwargs):
        captured.append(kwargs.get("user", ""))
        return {"text": "buscar_cliente", "model": "mock", "duration_ms": 1}

    monkeypatch.setattr(llm_client, "call_llm", _capture)
    result = ii.infer_goal_from_path(
        ["FrmLogin.aspx", "FrmLogin.aspx", "FrmBusqueda.aspx"]
    )
    assert result.ok
    # The user prompt should only contain FrmLogin.aspx once
    assert captured
    assert captured[0].count("FrmLogin.aspx") == 1


def test_infer_goal_normalised_label_returns_low(monkeypatch):
    """LLM returning label in a different case → low confidence match."""
    import intent_inferrer as ii
    import llm_client
    monkeypatch.setattr(
        llm_client, "call_llm",
        lambda **kwargs: {"text": "Buscar_Cliente", "model": "mock", "duration_ms": 1},
    )
    result = ii.infer_goal_from_path(["FrmLogin.aspx", "FrmBusqueda.aspx"])
    assert result.ok
    assert result.goal_action == "buscar_cliente"
    assert result.confidence == "low"


# ── infer_from_session_file() ─────────────────────────────────────────────────

def test_infer_from_session_file_reads_nav_path(tmp_path, monkeypatch):
    import intent_inferrer as ii
    import llm_client
    monkeypatch.setattr(
        llm_client, "call_llm",
        lambda **kwargs: {"text": "buscar_cliente", "model": "mock", "duration_ms": 1},
    )
    session_data = {
        "navigation_path": ["FrmLogin.aspx", "FrmBusqueda.aspx"],
        "goal": "",
    }
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps(session_data), encoding="utf-8")

    result = ii.infer_from_session_file(session_file)
    assert result.ok
    assert result.goal_action == "buscar_cliente"


def test_infer_from_session_file_accepts_parent_dir(tmp_path, monkeypatch):
    import intent_inferrer as ii
    import llm_client
    monkeypatch.setattr(
        llm_client, "call_llm",
        lambda **kwargs: {"text": "buscar_cliente", "model": "mock", "duration_ms": 1},
    )
    session_data = {"navigation_path": ["FrmLogin.aspx", "FrmBusqueda.aspx"]}
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps(session_data), encoding="utf-8")

    # Pass parent directory instead of the file
    result = ii.infer_from_session_file(tmp_path)
    assert result.ok


def test_infer_from_session_file_missing_file():
    import intent_inferrer as ii
    result = ii.infer_from_session_file(Path("/nonexistent/path/session.json"))
    assert not result.ok
    assert "not found" in result.error.lower()


def test_infer_from_session_file_empty_nav_path(tmp_path):
    import intent_inferrer as ii
    session_data = {"navigation_path": []}
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps(session_data), encoding="utf-8")
    result = ii.infer_from_session_file(session_file)
    assert result.ok  # soft failure
    assert result.goal_action == ""
    assert result.confidence == "unknown"


# ── intent_parser integration ─────────────────────────────────────────────────

def test_intent_parser_infers_goal_action_from_nav_path(tmp_path, monkeypatch):
    """When intent_spec has navigation_path but no goal_action, inferrer is used."""
    import intent_parser as ip
    import intent_inferrer as ii

    fake_infer_result = ii.InferResult(
        ok=True,
        goal_action="buscar_cliente",
        confidence="high",
        raw_response="buscar_cliente",
        model="mock",
        duration_ms=5,
    )
    monkeypatch.setattr(ii, "infer_goal_from_path", lambda path: fake_infer_result)
    monkeypatch.setattr(ip, "_intent_inferrer", ii, raising=False)
    monkeypatch.setattr(ip, "_INFERRER_AVAILABLE", True)

    spec = {
        "intent_raw": "buscar cliente",
        "goal_action": "",
        "navigation_path": ["FrmLogin.aspx", "FrmBusqueda.aspx"],
        "test_cases": [{"id": "T1", "description": "buscar", "expected": "resultados"}],
    }
    spec_file = tmp_path / "intent_spec.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    result = ip.run(spec_file)
    assert result["ok"]
    assert result["intent_spec"]["goal_action"] == "buscar_cliente"
    assert result["meta"]["inferrer_used"] is True
    assert result["meta"]["inferrer_suggestion"] == "buscar_cliente"


def test_intent_parser_does_not_override_existing_goal_action(tmp_path, monkeypatch):
    """If goal_action is already set, inferrer must NOT replace it."""
    import intent_parser as ip
    import intent_inferrer as ii

    fake_infer_result = ii.InferResult(
        ok=True,
        goal_action="otra_cosa",
        confidence="high",
        raw_response="otra_cosa",
        model="mock",
        duration_ms=5,
    )
    monkeypatch.setattr(ii, "infer_goal_from_path", lambda path: fake_infer_result)
    monkeypatch.setattr(ip, "_intent_inferrer", ii, raising=False)
    monkeypatch.setattr(ip, "_INFERRER_AVAILABLE", True)

    spec = {
        "intent_raw": "buscar cliente",
        "goal_action": "buscar_cliente",  # already set
        "navigation_path": ["FrmLogin.aspx", "FrmBusqueda.aspx"],
        "test_cases": [{"id": "T1", "description": "buscar", "expected": "resultados"}],
    }
    spec_file = tmp_path / "intent_spec.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    result = ip.run(spec_file)
    assert result["ok"]
    assert result["intent_spec"]["goal_action"] == "buscar_cliente"
    assert result["meta"]["inferrer_used"] is False


def test_intent_parser_skips_unknown_confidence_inference(tmp_path, monkeypatch):
    """Inferrer returning confidence='unknown' must NOT set goal_action."""
    import intent_parser as ip
    import intent_inferrer as ii

    fake_infer_result = ii.InferResult(
        ok=True,
        goal_action="",
        confidence="unknown",
        raw_response="unknown",
        model="mock",
        duration_ms=5,
    )
    monkeypatch.setattr(ii, "infer_goal_from_path", lambda path: fake_infer_result)
    monkeypatch.setattr(ip, "_intent_inferrer", ii, raising=False)
    monkeypatch.setattr(ip, "_INFERRER_AVAILABLE", True)

    spec = {
        "intent_raw": "hacer algo",
        "goal_action": "",
        "navigation_path": ["FrmLogin.aspx", "FrmBusqueda.aspx"],
        "test_cases": [{"id": "T1", "description": "algo", "expected": "algo"}],
    }
    spec_file = tmp_path / "intent_spec.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    result = ip.run(spec_file)
    assert result["ok"]
    assert result["intent_spec"]["goal_action"] == ""
    assert result["meta"]["inferrer_used"] is False


def test_intent_parser_meta_has_inferrer_fields(tmp_path, monkeypatch):
    """meta dict always has inferrer_used, inferrer_suggestion, inferrer_confidence."""
    import intent_parser as ip
    monkeypatch.setattr(ip, "_INFERRER_AVAILABLE", False)

    spec = {
        "intent_raw": "buscar",
        "goal_action": "buscar_cliente",
        "test_cases": [{"id": "T1", "description": "buscar", "expected": "algo"}],
    }
    spec_file = tmp_path / "intent_spec.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    result = ip.run(spec_file)
    assert result["ok"]
    meta = result["meta"]
    assert "inferrer_used" in meta
    assert "inferrer_suggestion" in meta
    assert "inferrer_confidence" in meta


# ── session_recorder._build_session_payload integration ──────────────────────

def test_session_recorder_payload_has_inferred_goal_action_field():
    """_build_session_payload always includes inferred_goal_action in the dict."""
    import session_recorder as sr
    payload = sr._build_session_payload(
        goal="test",
        started_at="2026-05-05T00:00:00",
        navigation_path=["FrmLogin.aspx", "FrmBusqueda.aspx"],
        transitions=[],
        discovered_selectors={},
        form_fields={},
        request_log=[],
    )
    assert "inferred_goal_action" in payload
    assert payload["inferred_goal_action"] == ""


def test_session_recorder_payload_with_explicit_inferred_goal():
    import session_recorder as sr
    payload = sr._build_session_payload(
        goal="",
        started_at="2026-05-05T00:00:00",
        navigation_path=["FrmLogin.aspx", "FrmBusqueda.aspx"],
        transitions=[],
        discovered_selectors={},
        form_fields={},
        request_log=[],
        inferred_goal_action="buscar_cliente",
    )
    assert payload["inferred_goal_action"] == "buscar_cliente"
