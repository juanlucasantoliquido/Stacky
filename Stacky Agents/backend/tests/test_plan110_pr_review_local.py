"""Plan 110 F5 — Revisión con modelo local: UN prompt autocontenido + contexto completo (v2.1)."""
import os
import types
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def app_on():
    import config as cfg
    saved = {k: getattr(cfg.config, k, None) for k in (
        "STACKY_PR_REVIEWER_ENABLED", "LOCAL_LLM_ENABLED",
        "STACKY_PR_REVIEW_DIFF_MAX_CHARS", "STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS",
    )}
    cfg.config.STACKY_PR_REVIEWER_ENABLED = True
    cfg.config.LOCAL_LLM_ENABLED = True
    cfg.config.STACKY_PR_REVIEW_DIFF_MAX_CHARS = 60000
    cfg.config.STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS = 200000
    from app import create_app
    from db import init_db
    app = create_app()
    app.config["TESTING"] = True
    init_db()
    yield app
    for k, v in saved.items():
        setattr(cfg.config, k, v)


@pytest.fixture
def app_reviewer_off():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_PR_REVIEWER_ENABLED", False)
    cfg.config.STACKY_PR_REVIEWER_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PR_REVIEWER_ENABLED = orig


def _provider(diff_text="diff normal"):
    provider = mock.MagicMock()
    provider.name = "gitlab"
    provider.get_merge_request.return_value = {
        "id": "7", "state": "open", "pipeline_status": "success", "mergeable": True,
        "source_branch": "feat", "target_branch": "main", "web_url": "u",
    }
    provider.get_merge_request_diff.return_value = {
        "id": "7", "files": [{"path": "a.py", "change_type": "modified"}],
        "diff_text": diff_text, "diff_available": True, "note": "",
    }
    return provider


def _resp(text):
    return types.SimpleNamespace(text=text, metadata={"model": "qwen3:32b"})


def test_review_local_404_when_reviewer_flag_off(app_reviewer_off):
    c = app_reviewer_off.test_client()
    assert c.post("/api/pr-review/review/local", json={"project": "p", "mr_id": "7"}).status_code == 404


def test_review_local_400_when_local_llm_off(app_on):
    import config as cfg
    cfg.config.LOCAL_LLM_ENABLED = False
    c = app_on.test_client()
    resp = c.post("/api/pr-review/review/local", json={"project": "p", "mr_id": "7"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "local_llm_disabled"
    cfg.config.LOCAL_LLM_ENABLED = True


def test_local_review_single_self_contained_prompt(app_on):
    c = app_on.test_client()
    captured = {}

    def _fake(**kwargs):
        captured.update(kwargs)
        return _resp("respuesta")

    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider()):
        with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_fake):
            resp = c.post("/api/pr-review/review/local",
                          json={"project": "p", "mr_id": "7", "title": "Mi PR"})
    assert resp.status_code == 200
    user = captured["user"]
    assert "Mi PR" in user
    assert "feat → main" in user
    assert "Pipeline: success" in user
    assert "== DIFF" in user
    assert "== PREGUNTA DEL OPERADOR ==" in user


def test_local_review_uses_operator_question(app_on):
    c = app_on.test_client()
    captured = {}
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider()):
        with mock.patch("copilot_bridge.invoke_local_llm", side_effect=lambda **k: captured.update(k) or _resp("r")):
            c.post("/api/pr-review/review/local",
                   json={"project": "p", "mr_id": "7", "question": "¿por qué toca el schema?"})
    assert "¿por qué toca el schema?" in captured["user"]


def test_local_review_never_stores_raw_diff(app_on):
    c = app_on.test_client()
    sentinel = "SENTINEL_LOCAL_DIFF_99"
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider(sentinel)):
        with mock.patch("copilot_bridge.invoke_local_llm", return_value=_resp("r")):
            resp = c.post("/api/pr-review/review/local", json={"project": "p", "mr_id": "7"})
    execution_id = resp.get_json()["execution_id"]
    from db import session_scope
    from models import AgentExecution
    with session_scope() as s:
        ex = s.get(AgentExecution, execution_id)
        assert sentinel not in (ex.input_context_json or "")


def test_local_review_uses_full_untruncated_context(app_on):
    """v2.1 — diff > cap Haiku (60000) pero < cap local (200000) llega ÍNTEGRO."""
    c = app_on.test_client()
    marker = "FIN_DEL_DIFF_MARKER"
    big_diff = ("linea de diff\n" * 8000) + marker  # ~104k chars > 60000, < 200000
    assert len(big_diff) > 60000 and len(big_diff) < 200000
    captured = {}
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider(big_diff)):
        with mock.patch("copilot_bridge.invoke_local_llm", side_effect=lambda **k: captured.update(k) or _resp("r")):
            resp = c.post("/api/pr-review/review/local", json={"project": "p", "mr_id": "7"})
    assert marker in captured["user"]  # diff íntegro, sin truncar
    assert "truncado por tamaño" not in captured["user"]
    assert resp.get_json()["diff_truncated"] is False


def test_local_cap_zero_means_unlimited(app_on):
    """v2.1 — cap 0 = sin límite: diff enorme llega completo."""
    import config as cfg
    cfg.config.STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS = 0
    c = app_on.test_client()
    marker = "FIN_DIFF_ENORME"
    huge = ("x" * 500000) + marker
    captured = {}
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider(huge)):
        with mock.patch("copilot_bridge.invoke_local_llm", side_effect=lambda **k: captured.update(k) or _resp("r")):
            resp = c.post("/api/pr-review/review/local", json={"project": "p", "mr_id": "7"})
    assert marker in captured["user"]
    assert resp.get_json()["diff_truncated"] is False
    cfg.config.STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS = 200000
