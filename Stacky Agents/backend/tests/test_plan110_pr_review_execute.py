"""Plan 110 F6 — /execute con conjunto CERRADO de acciones + HITL fuerte en merge."""
import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def app_on():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_PR_REVIEWER_ENABLED", False)
    cfg.config.STACKY_PR_REVIEWER_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PR_REVIEWER_ENABLED = orig


@pytest.fixture
def app_off():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_PR_REVIEWER_ENABLED", False)
    cfg.config.STACKY_PR_REVIEWER_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PR_REVIEWER_ENABLED = orig


class _FakeGitLab:
    """Provider fake CON approve (capability)."""
    name = "gitlab"
    def __init__(self):
        self.calls = []
    def comment_merge_request(self, mr_id, body):
        self.calls.append(("comment", mr_id, body)); return {"ok": True, "id": "n1"}
    def close_merge_request(self, mr_id):
        self.calls.append(("close", mr_id)); return {"ok": True, "id": mr_id, "state": "closed"}
    def merge_merge_request(self, mr_id):
        self.calls.append(("merge", mr_id)); return {"ok": True, "id": mr_id, "state": "merged"}
    def approve_merge_request(self, mr_id):
        self.calls.append(("approve", mr_id)); return {"ok": True, "id": mr_id, "approved": True}


class _FakeAdo:
    """Provider fake SIN approve (ADO v1)."""
    name = "azure_devops"
    def __init__(self):
        self.calls = []
    def comment_merge_request(self, mr_id, body):
        self.calls.append(("comment", mr_id, body)); return {"ok": True, "id": "t1"}
    def close_merge_request(self, mr_id):
        self.calls.append(("close", mr_id)); return {"ok": True, "id": mr_id, "state": "closed"}
    def merge_merge_request(self, mr_id):
        self.calls.append(("merge", mr_id)); return {"ok": True, "id": mr_id, "state": "merged"}


def test_execute_404_when_flag_off(app_off):
    c = app_off.test_client()
    assert c.post("/api/pr-review/execute", json={"project": "p", "mr_id": "7", "action": "merge"}).status_code == 404


def test_none_is_noop(app_on):
    c = app_on.test_client()
    with mock.patch("api.pr_review.get_merge_request_provider") as gp:
        resp = c.post("/api/pr-review/execute", json={"project": "p", "mr_id": "7", "action": "none"})
        assert resp.status_code == 200
        assert resp.get_json()["result"]["noop"] is True
        gp.assert_not_called()


def test_unknown_action_400(app_on):
    c = app_on.test_client()
    resp = c.post("/api/pr-review/execute", json={"project": "p", "mr_id": "7", "action": "delete_repo"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "action_not_allowed"


def test_comment_requires_confirm_and_body(app_on):
    c = app_on.test_client()
    prov = _FakeGitLab()
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=prov):
        # falta confirm
        r1 = c.post("/api/pr-review/execute", json={"project": "p", "mr_id": "7", "action": "comment", "body": "hola"})
        assert r1.status_code == 400
        # falta body
        r2 = c.post("/api/pr-review/execute", json={"project": "p", "mr_id": "7", "action": "comment", "confirm": True})
        assert r2.status_code == 400
        assert prov.calls == []
        # ambos
        r3 = c.post("/api/pr-review/execute",
                    json={"project": "p", "mr_id": "7", "action": "comment", "confirm": True, "body": "hola"})
        assert r3.status_code == 200
        assert prov.calls == [("comment", "7", "hola")]


def test_merge_requires_double_confirm(app_on):
    c = app_on.test_client()
    prov = _FakeGitLab()
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=prov):
        r1 = c.post("/api/pr-review/execute", json={"project": "p", "mr_id": "7", "action": "merge", "confirm": True})
        assert r1.status_code == 400
        assert r1.get_json()["error"] == "confirm_merge_required"
        assert prov.calls == []
        r2 = c.post("/api/pr-review/execute",
                    json={"project": "p", "mr_id": "7", "action": "merge", "confirm": True, "confirm_merge": True})
        assert r2.status_code == 200
        assert prov.calls == [("merge", "7")]


def test_close_calls_close_merge_request(app_on):
    c = app_on.test_client()
    prov = _FakeGitLab()
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=prov):
        resp = c.post("/api/pr-review/execute", json={"project": "p", "mr_id": "7", "action": "close", "confirm": True})
        assert resp.status_code == 200
        assert prov.calls == [("close", "7")]


def test_approve_capability_gated(app_on):
    c = app_on.test_client()
    # ADO sin approve → 400
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_FakeAdo()):
        r1 = c.post("/api/pr-review/execute", json={"project": "p", "mr_id": "7", "action": "approve", "confirm": True})
        assert r1.status_code == 400
    # GitLab con approve → llama
    prov = _FakeGitLab()
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=prov):
        r2 = c.post("/api/pr-review/execute", json={"project": "p", "mr_id": "7", "action": "approve", "confirm": True})
        assert r2.status_code == 200
        assert prov.calls == [("approve", "7")]


def test_actions_endpoint_reports_capability(app_on):
    c = app_on.test_client()
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_FakeGitLab()):
        gl = c.get("/api/pr-review/actions?project=p").get_json()
        assert "approve" in gl["actions"]
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_FakeAdo()):
        ado = c.get("/api/pr-review/actions?project=p").get_json()
        assert "approve" not in ado["actions"]


# ── Unit providers ─────────────────────────────────────────────────────────────
def test_gitlab_comment_close_approve_urls():
    from services.gitlab_provider import GitLabTrackerProvider
    p = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    p._project = "org/repo"
    client = mock.MagicMock()
    client._project_path.return_value = "org/repo"
    client._request.return_value = ({"id": 55}, {})
    p._client = client

    p.comment_merge_request("7", "hola")
    args, kwargs = client._request.call_args
    assert args[0] == "POST" and "/merge_requests/7/notes" in args[1]
    assert kwargs["json_body"]["body"] == "hola"

    p.close_merge_request("7")
    args, kwargs = client._request.call_args
    assert args[0] == "PUT" and kwargs["json_body"]["state_event"] == "close"

    p.approve_merge_request("7")
    args, _ = client._request.call_args
    assert args[0] == "POST" and "/approve" in args[1]


def test_ado_comment_close_urls():
    from services.ado_provider import AdoTrackerProvider
    p = AdoTrackerProvider.__new__(AdoTrackerProvider)
    p._project = "MyProject"
    client = mock.MagicMock()
    client._base_proj = "https://dev.azure.com/org/MyProject"
    client._request.return_value = {"id": 9}
    p._client = client
    with mock.patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-1"):
        p.comment_merge_request("7", "hola")
        args, kwargs = client._request.call_args
        assert args[0] == "POST" and "/pullRequests/7/threads" in args[1]
        assert kwargs["body"]["comments"][0]["content"] == "hola"

        p.close_merge_request("7")
        args, kwargs = client._request.call_args
        assert args[0] == "PATCH" and kwargs["body"]["status"] == "abandoned"
