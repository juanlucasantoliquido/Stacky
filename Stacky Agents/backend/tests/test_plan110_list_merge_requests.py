"""Plan 110 F1 — list_merge_requests + get_merge_request_diff en el puerto MR/PR.

Providers reales (GitLab, ADO) con _client._request mockeado. Verifica el shape
normalizado, el vocabulario de estado compartido (open/merged/closed) y la
degradación controlada de ADO (diff_available=False).
"""
from unittest.mock import MagicMock, patch


def _gitlab():
    from services.gitlab_provider import GitLabTrackerProvider
    p = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    p._project = "myorg/myrepo"
    client = MagicMock()
    client._project_path.return_value = "myorg/myrepo"
    p._client = client
    return p, client


def _ado():
    from services.ado_provider import AdoTrackerProvider
    p = AdoTrackerProvider.__new__(AdoTrackerProvider)
    p._project = "MyProject"
    client = MagicMock()
    client._base_proj = "https://dev.azure.com/org/MyProject"
    p._client = client
    return p, client


def test_protocol_surface_includes_new_methods():
    from services.merge_request_provider import MR_PORT_METHODS
    assert "list_merge_requests" in MR_PORT_METHODS
    assert "get_merge_request_diff" in MR_PORT_METHODS


def test_gitlab_list_normalizes_state_and_pipeline():
    p, client = _gitlab()
    client._request.return_value = (
        [
            {
                "iid": 7, "title": "Add feature", "state": "opened",
                "source_branch": "feature/x", "target_branch": "main",
                "author": {"name": "Ana"}, "web_url": "https://gl/mr/7",
                "head_pipeline": {"status": "success"},
            }
        ],
        {},
    )
    rows = p.list_merge_requests("open")
    assert len(rows) == 1
    mr = rows[0]
    assert mr["id"] == "7"
    assert mr["state"] == "open"  # opened → open
    assert mr["source_branch"] == "feature/x"
    assert mr["target_branch"] == "main"
    assert mr["author"] == "Ana"
    assert mr["pipeline_status"] == "success"
    # state param se mapea a gl 'opened'
    _, kwargs = client._request.call_args
    assert kwargs["params"]["state"] == "opened"


def test_gitlab_get_diff_builds_files_and_text():
    p, client = _gitlab()
    client._request.return_value = (
        {
            "changes": [
                {"new_path": "a.py", "old_path": "a.py", "diff": "@@ -1 +1 @@\n-x\n+y"},
                {"new_path": "b.py", "old_path": None, "new_file": True, "diff": "+nuevo"},
            ]
        },
        {},
    )
    out = p.get_merge_request_diff("7")
    assert out["diff_available"] is True
    assert out["id"] == "7"
    paths = {f["path"]: f["change_type"] for f in out["files"]}
    assert paths["a.py"] == "modified"
    assert paths["b.py"] == "added"
    assert "a.py" in out["diff_text"] and "+y" in out["diff_text"]


def test_ado_list_normalizes_status_and_refs():
    p, client = _ado()
    with patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-1"):
        client._request.return_value = {
            "value": [
                {
                    "pullRequestId": 12, "title": "Fix bug", "status": "active",
                    "sourceRefName": "refs/heads/fix/y", "targetRefName": "refs/heads/main",
                    "createdBy": {"displayName": "Beto"},
                    "_links": {"web": {"href": "https://ado/pr/12"}},
                }
            ]
        }
        rows = p.list_merge_requests("open")
    assert len(rows) == 1
    mr = rows[0]
    assert mr["id"] == "12"
    assert mr["state"] == "open"  # active → open
    assert mr["source_branch"] == "fix/y"  # refs/heads/ stripped
    assert mr["target_branch"] == "main"
    assert mr["author"] == "Beto"


def test_ado_get_diff_degrades_gracefully():
    p, client = _ado()
    with patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-1"):
        client._request.side_effect = [
            {"value": [{"id": 3}]},  # iterations
            {"changeEntries": [  # changes of last iteration
                {"item": {"path": "/src/a.py"}, "changeType": "edit"},
                {"item": {"path": "/src/b.py"}, "changeType": "add"},
            ]},
        ]
        out = p.get_merge_request_diff("12")
    assert out["diff_available"] is False
    assert out["diff_text"] == ""
    assert out["note"]  # hint no vacío
    paths = {f["path"]: f["change_type"] for f in out["files"]}
    assert paths["/src/a.py"] == "modified"
    assert paths["/src/b.py"] == "added"
