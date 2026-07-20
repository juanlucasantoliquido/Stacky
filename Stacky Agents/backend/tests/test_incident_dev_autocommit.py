"""Plan 177 F4 — post-hook `incident_dev_autocommit`: commit + PR con los tests.

Mockea el proveedor MR (get_repo_writer / get_merge_request_provider), el comentario
agnóstico (services.tracker_provider.get_tracker_provider) y las funciones de
`incident_dev_pr`. Ejercita la lógica del hook end to end sin git ni red.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import services.incident_dev_autocommit as mod
from services import incident_dev_pr


# ── Fakes del proveedor MR / tracker ──────────────────────────────────────────

class _FakeWriter:
    def __init__(self):
        self.commits = []

    def commit_file(self, path, content, branch, message):
        self.commits.append({"path": path, "content": content, "branch": branch, "message": message})
        return {"status": "create", "sha": "sha", "path": path, "branch": branch, "web_url": "u"}


class _FakeMRP:
    name = "azure_devops"

    def __init__(self, raise_create=False):
        self.created = []
        self._raise = raise_create

    def create_merge_request(self, source_branch, target_branch, title, description):
        if self._raise:
            raise RuntimeError("boom-create")
        self.created.append({"source": source_branch, "target": target_branch,
                             "title": title, "description": description})
        return {"id": "42", "web_url": "https://pr.example/42", "state": "open"}


class _FakeClient:
    def __init__(self, base_proj):
        self._base_proj = base_proj


class _FakeTracker:
    def __init__(self, base_proj="https://dev.azure.com/orgA/proj"):
        self._client = _FakeClient(base_proj)
        self.comments = []

    def post_comment(self, item_id, body_html):
        self.comments.append({"item_id": item_id, "body": body_html})
        return {"ok": True, "id": "1"}


@contextmanager
def _patched(*, intent, changed=None, deleted=None, ado_id=100, project="proj",
             origin=None, provider_base="https://dev.azure.com/orgA/proj",
             read_none=False, flag=True, mrp=None):
    import config as cfg
    changed = changed if changed is not None else ["src/fix.py", "backend/tests/test_fix.py"]
    deleted = deleted or []
    writer = _FakeWriter()
    mrp = mrp or _FakeMRP()
    provider = _FakeTracker(base_proj=provider_base)
    mark = MagicMock()

    o_flag = getattr(cfg.config, "STACKY_INCIDENT_DEV_PR_ENABLED", False)
    cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = flag
    with ExitStack() as es:
        p = es.enter_context
        p(patch.object(incident_dev_pr, "get_intent", MagicMock(return_value=intent)))
        p(patch.object(incident_dev_pr, "snapshot_worktree", MagicMock(return_value={"entries": {}})))
        p(patch.object(incident_dev_pr, "compute_changed_files",
                       MagicMock(return_value={"added_or_modified": changed, "deleted": deleted})))
        p(patch.object(incident_dev_pr, "mark_intent", mark))
        p(patch.object(incident_dev_pr, "remote_origin_url", MagicMock(return_value=origin)))
        p(patch.object(mod, "_ticket_ado_id_and_project", MagicMock(return_value=(ado_id, project))))
        p(patch.object(mod, "_default_branch_for", MagicMock(return_value="main")))
        p(patch.object(mod, "_read_text_or_none",
                       MagicMock(return_value=None) if read_none
                       else MagicMock(side_effect=lambda root, rel: f"contenido de {rel}")))
        p(patch("services.repo_writer.get_repo_writer", MagicMock(return_value=writer)))
        p(patch("services.merge_request_provider.get_merge_request_provider", MagicMock(return_value=mrp)))
        p(patch("services.tracker_provider.get_tracker_provider", MagicMock(return_value=provider)))
        try:
            yield {"writer": writer, "mrp": mrp, "provider": provider, "mark": mark}
        finally:
            cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = o_flag


def _call(ticket_id=5, execution_id=77, final_status="completed", agent_type="incident_dev"):
    mod.maybe_open_pr_for_incident_dev(
        ticket_id=ticket_id, execution_id=execution_id,
        final_status=final_status, agent_type=agent_type, error=None,
    )


def _mark_status(mark, status):
    return [c for c in mark.call_args_list if c.kwargs.get("status") == status]


# ── 1-11 ──────────────────────────────────────────────────────────────────────

def test_opens_pr_with_code_and_tests():
    with _patched(intent={"open_pr": True}) as h:
        _call(ticket_id=5, execution_id=77)
    assert len(h["writer"].commits) == 2
    assert {c["branch"] for c in h["writer"].commits} == {"stacky/incidencia-5-exec-77"}
    assert len(h["mrp"].created) == 1
    opened = _mark_status(h["mark"], "opened")
    assert len(opened) == 1
    assert opened[0].kwargs["pr_url"] == "https://pr.example/42"
    desc = h["mrp"].created[0]["description"]
    assert "Tests incluidos" in desc
    assert "test_fix.py" in desc


def test_noop_when_delta_empty():
    with _patched(intent={"open_pr": True}, changed=[]) as h:
        _call()
    assert h["mrp"].created == []
    assert _mark_status(h["mark"], "blocked_empty")


def test_noop_when_no_intent():
    with _patched(intent=None) as h:
        _call()
    assert h["mrp"].created == []
    assert h["writer"].commits == []
    h["mark"].assert_not_called()


def test_noop_when_agent_type_not_incident_dev():
    with _patched(intent={"open_pr": True}) as h:
        _call(agent_type="developer")
    assert h["mrp"].created == []
    h["mark"].assert_not_called()


def test_noop_when_final_status_not_completed():
    with _patched(intent={"open_pr": True}) as h:
        _call(final_status="failed")
    assert h["mrp"].created == []
    h["mark"].assert_not_called()


def test_idempotent_when_already_opened():
    with _patched(intent={"open_pr": True, "status": "opened"}) as h:
        _call()
    assert h["mrp"].created == []
    h["mark"].assert_not_called()


def test_flag_off_is_noop():
    with _patched(intent={"open_pr": True}, flag=False) as h:
        _call()
    assert h["mrp"].created == []
    h["mark"].assert_not_called()


def test_error_is_not_silent():
    with _patched(intent={"open_pr": True}, mrp=_FakeMRP(raise_create=True)) as h:
        _call()  # NO debe relanzar
    assert h["mrp"].created == []
    assert _mark_status(h["mark"], "error")
    assert any("No se pudo abrir el PR" in c["body"] for c in h["provider"].comments)


def test_binary_files_skipped():
    with _patched(intent={"open_pr": True}, changed=["assets/logo.png"], read_none=True) as h:
        _call()
    assert h["mrp"].created == []
    assert _mark_status(h["mark"], "skipped")


def test_comment_uses_tracker_ado_id_not_local_pk():
    with _patched(intent={"open_pr": True}, ado_id=12345) as h:
        _call(ticket_id=5)
    # El comentario 🚀 usa el ado_id del tracker (str), NO la PK local "5".
    assert h["provider"].comments, "esperaba un comentario en la Issue"
    assert h["provider"].comments[-1]["item_id"] == "12345"
    assert all(c["item_id"] != "5" for c in h["provider"].comments)


def test_skip_when_worktree_maps_to_wrong_repo():
    with _patched(
        intent={"open_pr": True},
        origin="https://gitlab.other.example/orgB/repo.git",
        provider_base="https://dev.azure.com/orgA/proj",
    ) as h:
        _call()
    assert h["mrp"].created == []  # NO se abrió PR (host mismatch inequívoco)
    skipped = _mark_status(h["mark"], "skipped")
    assert skipped and "no mapea" in (skipped[0].kwargs.get("error") or "")
    assert any("otro remoto" in c["body"] for c in h["provider"].comments)
