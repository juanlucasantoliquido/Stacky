"""Fix modelo local 404 + análisis de estado de ticket con IA local.

Parte 1 — copilot_bridge.invoke_local_llm: si el server local devuelve 404
"model not found" (flag LOCAL_LLM_MODEL apuntando a un modelo no instalado),
hace fallback automático al mejor modelo instalado y reintenta UNA vez.

Parte 2 — POST /api/llm/ticket-insight/<id>: reúne épica + ticket + hijas +
comentarios + outputs de agentes y pide al modelo local resumen de estado,
puntos débiles e incoherencias.

Mocks: requests.post/get parcheados en copilot_bridge (gotcha plan 28);
invoke_local_llm parcheado en el módulo origen (import lazy en la ruta).
"""
import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


def _ok_payload(content="respuesta"):
    return {"choices": [{"message": {"content": content}}]}


_NOT_FOUND_BODY = (
    '{"error":{"message":"model \'qwen3:32b\' not found","type":"not_found_error"}}'
)

_INSTALLED = {
    "data": [
        {"id": "qwen2.5:3b"},
        {"id": "qwen2.5-coder:14b"},
        {"id": "qwen3-coder:30b-a3b-q4_K_M"},
        {"id": "deepseek-r1:14b"},
    ]
}


@pytest.fixture(autouse=True)
def _local_llm_config(monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENDPOINT", "http://localhost:11434/v1/chat/completions")
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_MODEL", "qwen3:32b")
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_TIMEOUT_SEC", 120)
    yield


# ── Parte 1: fallback de modelo en el bridge ─────────────────────────────────

def test_pick_fallback_same_base_other_tag():
    from copilot_bridge import _pick_fallback_local_model
    assert _pick_fallback_local_model("qwen3:32b", ["llama3", "qwen3:8b"]) == "qwen3:8b"


def test_pick_fallback_family_prefix():
    from copilot_bridge import _pick_fallback_local_model
    installed = ["qwen2.5:3b", "qwen3-coder:30b-a3b-q4_K_M", "deepseek-r1:14b"]
    assert _pick_fallback_local_model("qwen3:32b", installed) == "qwen3-coder:30b-a3b-q4_K_M"


def test_pick_fallback_stem_without_digits():
    from copilot_bridge import _pick_fallback_local_model
    installed = ["deepseek-r1:14b", "qwen2.5-coder:14b"]
    assert _pick_fallback_local_model("qwen3:32b", installed) == "qwen2.5-coder:14b"


def test_pick_fallback_last_resort_first_sorted():
    from copilot_bridge import _pick_fallback_local_model
    assert _pick_fallback_local_model("mistral:7b", ["zeta:1b", "alfa:1b"]) == "alfa:1b"


def test_pick_fallback_empty_installed_none():
    from copilot_bridge import _pick_fallback_local_model
    assert _pick_fallback_local_model("qwen3:32b", []) is None


def test_invoke_local_llm_404_retries_with_installed_model(monkeypatch):
    import copilot_bridge

    posts = mock.Mock(side_effect=[
        _FakeResponse(404, text=_NOT_FOUND_BODY),
        _FakeResponse(200, _ok_payload("hola desde el fallback")),
    ])
    monkeypatch.setattr(copilot_bridge.requests, "post", posts)
    monkeypatch.setattr(
        copilot_bridge.requests, "get",
        mock.Mock(return_value=_FakeResponse(200, _INSTALLED)),
    )

    logs = []
    result = copilot_bridge.invoke_local_llm(
        agent_type="x", system="s", user="u",
        on_log=lambda level, msg: logs.append((level, msg)),
    )
    assert result.text == "hola desde el fallback"
    assert result.metadata["model"] == "qwen3-coder:30b-a3b-q4_K_M"
    assert result.metadata["requested_model"] == "qwen3:32b"
    assert result.metadata["model_fallback"] is True
    # El reintento mandó el modelo fallback en el payload
    assert posts.call_args.kwargs["json"]["model"] == "qwen3-coder:30b-a3b-q4_K_M"
    assert any(level == "warn" and "no está instalado" in msg for level, msg in logs)


def test_invoke_local_llm_404_no_installed_models_raises_with_original(monkeypatch):
    import copilot_bridge

    monkeypatch.setattr(
        copilot_bridge.requests, "post",
        mock.Mock(return_value=_FakeResponse(404, text=_NOT_FOUND_BODY)),
    )
    monkeypatch.setattr(
        copilot_bridge.requests, "get",
        mock.Mock(return_value=_FakeResponse(200, {"data": []})),
    )
    with pytest.raises(RuntimeError, match="404"):
        copilot_bridge.invoke_local_llm(
            agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
        )


def test_invoke_local_llm_404_retry_fails_lists_installed(monkeypatch):
    import copilot_bridge

    monkeypatch.setattr(
        copilot_bridge.requests, "post",
        mock.Mock(return_value=_FakeResponse(404, text=_NOT_FOUND_BODY)),
    )
    monkeypatch.setattr(
        copilot_bridge.requests, "get",
        mock.Mock(return_value=_FakeResponse(200, _INSTALLED)),
    )
    with pytest.raises(RuntimeError, match="Modelos instalados"):
        copilot_bridge.invoke_local_llm(
            agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
        )


def test_invoke_local_llm_non_404_does_not_query_models(monkeypatch):
    import copilot_bridge

    mock_get = mock.Mock()
    monkeypatch.setattr(
        copilot_bridge.requests, "post",
        mock.Mock(return_value=_FakeResponse(500, text="server error")),
    )
    monkeypatch.setattr(copilot_bridge.requests, "get", mock_get)
    with pytest.raises(RuntimeError, match="500"):
        copilot_bridge.invoke_local_llm(
            agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
        )
    mock_get.assert_not_called()


def test_invoke_local_llm_happy_path_no_extra_requests(monkeypatch):
    import copilot_bridge

    mock_get = mock.Mock()
    monkeypatch.setattr(
        copilot_bridge.requests, "post",
        mock.Mock(return_value=_FakeResponse(200, _ok_payload("directo"))),
    )
    monkeypatch.setattr(copilot_bridge.requests, "get", mock_get)
    result = copilot_bridge.invoke_local_llm(
        agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
    )
    assert result.text == "directo"
    assert "model_fallback" not in (result.metadata or {})
    mock_get.assert_not_called()


# ── Parte 2: POST /api/llm/ticket-insight/<id> ───────────────────────────────

@pytest.fixture
def app_flag_on():
    import config as cfg
    orig = getattr(cfg.config, "LOCAL_LLM_ENABLED", False)
    cfg.config.LOCAL_LLM_ENABLED = True
    from app import create_app
    from db import init_db
    app = create_app()
    app.config["TESTING"] = True
    init_db()
    yield app
    cfg.config.LOCAL_LLM_ENABLED = orig


@pytest.fixture
def app_flag_off():
    import config as cfg
    orig = getattr(cfg.config, "LOCAL_LLM_ENABLED", False)
    cfg.config.LOCAL_LLM_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.LOCAL_LLM_ENABLED = orig


_ADO_ID_SEQ = iter(range(900, 100000, 10))


def _make_ticket_tree():
    """Épica N → ticket N+1 (con 1 ejecución) → task hija N+2 (ids únicos por corrida)."""
    from datetime import datetime

    from db import session_scope
    from models import AgentExecution, Ticket

    base = next(_ADO_ID_SEQ)
    with session_scope() as s:
        epic = Ticket(
            ado_id=base, project="Proj", stacky_project_name="Proj",
            title="Épica de facturación", work_item_type="Epic", ado_state="Active",
        )
        s.add(epic)
        ticket = Ticket(
            ado_id=base + 1, project="Proj", stacky_project_name="Proj",
            title="Implementar recargo nocturno", work_item_type="Feature",
            ado_state="Active", parent_ado_id=base,
            description="El recargo debe aplicarse entre 22 y 6.",
        )
        s.add(ticket)
        child = Ticket(
            ado_id=base + 2, project="Proj", stacky_project_name="Proj",
            title="Task hija de recargo", work_item_type="Task",
            ado_state="New", parent_ado_id=base + 1,
        )
        s.add(child)
        s.flush()
        ex = AgentExecution(
            ticket_id=ticket.id, agent_type="developer", status="completed",
            verdict="approved", input_context_json="[]",
            output="Implementé el recargo con un cron a las 23.",
            started_by="test", started_at=datetime.utcnow(),
        )
        s.add(ex)
        s.flush()
        return ticket.id


def test_ticket_insight_flag_off_404(app_flag_off):
    c = app_flag_off.test_client()
    assert c.post("/api/llm/ticket-insight/1", json={}).status_code == 404


def test_ticket_insight_ticket_not_found_404(app_flag_on):
    c = app_flag_on.test_client()
    r = c.post("/api/llm/ticket-insight/999999", json={})
    assert r.status_code == 404
    assert r.get_json()["error"] == "ticket_not_found"


def test_ticket_insight_happy_path_builds_full_context(app_flag_on):
    ticket_id = _make_ticket_tree()
    c = app_flag_on.test_client()
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(
            text="## Resumen del estado\nTodo bien.",
            format="markdown",
            metadata={"model": "qwen3-coder:30b-a3b-q4_K_M"},
        )

    fake_comments = [{"author": "Juan", "date": "2026-07-13", "text": "Falta probar en TEST"}]
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy), \
         mock.patch("api.local_llm_analysis._fetch_ticket_comments_safe", return_value=fake_comments):
        r = c.post(f"/api/llm/ticket-insight/{ticket_id}", json={"question": "¿está listo?"})

    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["analysis"].startswith("## Resumen del estado")
    assert body["model"] == "qwen3-coder:30b-a3b-q4_K_M"
    assert body["context_stats"] == {
        "has_epic": True, "children": 1, "comments": 1, "executions": 1,
    }

    prompt = captured["user"]
    assert "Implementar recargo nocturno" in prompt          # ticket
    assert "Épica de facturación" in prompt                   # épica padre
    assert "Task hija de recargo" in prompt                    # hija
    assert "Falta probar en TEST" in prompt                    # comentario
    assert "Implementé el recargo con un cron" in prompt       # output de agente
    assert "¿está listo?" in prompt                            # pregunta del operador
    assert "Incoherencias detectadas" in prompt                # secciones pedidas
    assert "REGLA ABSOLUTA (HITL)" in captured["system"]

    # La ejecución quedó registrada sobre el ticket REAL (no el interno -5)
    from db import session_scope
    from models import AgentExecution
    with session_scope() as s:
        ex = s.get(AgentExecution, body["execution_id"])
        assert ex is not None
        assert ex.ticket_id == ticket_id
        assert ex.agent_type == "local_llm_ticket_insight"
        assert ex.status == "completed"


def test_ticket_insight_bridge_error_502_marks_execution(app_flag_on):
    ticket_id = _make_ticket_tree()
    c = app_flag_on.test_client()
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("boom local")), \
         mock.patch("api.local_llm_analysis._fetch_ticket_comments_safe", return_value=[]):
        r = c.post(f"/api/llm/ticket-insight/{ticket_id}", json={})
    assert r.status_code == 502
    body = r.get_json()
    assert body["ok"] is False
    from db import session_scope
    from models import AgentExecution
    with session_scope() as s:
        ex = s.get(AgentExecution, body["execution_id"])
        assert ex.status == "error"
        assert "boom local" in (ex.error_message or "")


def test_ticket_insight_forwards_optional_model(app_flag_on):
    ticket_id = _make_ticket_tree()
    c = app_flag_on.test_client()
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(text="ok", format="markdown", metadata={"model": "deepseek-r1:14b"})

    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy), \
         mock.patch("api.local_llm_analysis._fetch_ticket_comments_safe", return_value=[]):
        c.post(f"/api/llm/ticket-insight/{ticket_id}", json={"model": "deepseek-r1:14b"})
    assert captured["model"] == "deepseek-r1:14b"
