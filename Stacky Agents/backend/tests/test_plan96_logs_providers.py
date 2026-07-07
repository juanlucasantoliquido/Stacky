"""
Plan 96 F2 — Sub-puerto CILogsProvider + adapters GitLab y ADO.
Mocks HTTP (_request / _request_paginated); paridad de contrato entre trackers.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.ci_logs_provider import CILogsProvider, LOGS_PORT_METHODS, get_ci_logs_provider
from services.tracker_provider import TrackerApiError, TrackerConfigError


# ---------------------------------------------------------------------------
# Factory + conformidad estructural
# ---------------------------------------------------------------------------

def test_f2_factory_and_structural_conformance():
    """La fábrica despacha por tracker_type y los adapters cumplen el Protocol."""
    from services.gitlab_ci_logs import GitLabCILogsProvider
    from services.ado_ci_logs import AdoCILogsProvider

    assert LOGS_PORT_METHODS == ("list_failed_jobs", "get_job_log")

    with patch("services.gitlab_provider.GitLabClient"):
        gl = GitLabCILogsProvider(project="proj")
    assert isinstance(gl, CILogsProvider)
    assert gl.name == "gitlab"

    with patch("services.project_context.build_ado_client", return_value=MagicMock()):
        ado = AdoCILogsProvider(project="proj")
    assert isinstance(ado, CILogsProvider)
    assert ado.name == "azure_devops"


def test_f2_factory_gitlab_flag_off_raises_config_error():
    """gitlab sin STACKY_GITLAB_ENABLED ⇒ TrackerConfigError (espejo get_ci_provider)."""
    ctx = MagicMock(tracker_type="gitlab")
    with patch("services.project_context.resolve_project_context", return_value=ctx), \
         patch("config.config") as mock_cfg:
        mock_cfg.STACKY_GITLAB_ENABLED = False
        with pytest.raises(TrackerConfigError):
            get_ci_logs_provider(project="proj")


def test_f2_factory_unknown_tracker_raises_config_error():
    ctx = MagicMock(tracker_type="unknown_tracker")
    with patch("services.project_context.resolve_project_context", return_value=ctx):
        with pytest.raises(TrackerConfigError):
            get_ci_logs_provider(project="proj")


# ---------------------------------------------------------------------------
# GitLab adapter
# ---------------------------------------------------------------------------

def _make_gitlab_provider():
    from services.gitlab_ci_logs import GitLabCILogsProvider
    with patch("services.gitlab_provider.GitLabClient"):
        provider = GitLabCILogsProvider(project="proj")
    provider._client = MagicMock()
    provider._client._project_path.return_value = "group%2Fproj"
    return provider


def test_f2_gitlab_failed_jobs_mapped():
    """list_failed_jobs mapea id/name/stage/web_url (passthrough) — paginado real."""
    provider = _make_gitlab_provider()
    provider._client._request_paginated.return_value = [
        {"id": 101, "name": "build", "stage": "build", "web_url": "https://gitlab.example/jobs/101"},
        {"id": 102, "name": "test", "stage": "test", "web_url": "https://gitlab.example/jobs/102"},
    ]

    jobs = provider.list_failed_jobs("55")

    assert jobs == [
        {"job_id": "101", "name": "build", "stage": "build", "web_url": "https://gitlab.example/jobs/101"},
        {"job_id": "102", "name": "test", "stage": "test", "web_url": "https://gitlab.example/jobs/102"},
    ]
    provider._client._request_paginated.assert_called_once_with(
        "/projects/group%2Fproj/pipelines/55/jobs",
        params={"scope[]": "failed"},
    )


def test_f2_gitlab_trace_text():
    """get_job_log devuelve el texto crudo del trace."""
    provider = _make_gitlab_provider()
    provider._client._request.return_value = ("some log text\nmore lines", {})

    log = provider.get_job_log("101")

    assert log == "some log text\nmore lines"
    provider._client._request.assert_called_once_with(
        "GET", "/projects/group%2Fproj/jobs/101/trace"
    )


def test_f2_gitlab_empty_trace_returns_str():
    """_request devuelve ({}, headers) para trace vacío ⇒ get_job_log retorna '' (no dict)."""
    provider = _make_gitlab_provider()
    provider._client._request.return_value = ({}, {})

    log = provider.get_job_log("101")

    assert log == ""
    assert isinstance(log, str)


# ---------------------------------------------------------------------------
# ADO adapter
# ---------------------------------------------------------------------------

def _make_ado_provider():
    from services.ado_ci_logs import AdoCILogsProvider
    mock_client = MagicMock()
    mock_client._base_proj = "https://dev.azure.com/org/proj"
    with patch("services.project_context.build_ado_client", return_value=mock_client):
        provider = AdoCILogsProvider(project="proj")
    return provider


def test_f2_ado_timeline_failed_tasks_mapped():
    """Fixture mixta: Task failed con log, Task succeeded, Task canceled (excluida),
    Phase, Task failed sin log — solo 1 en el resultado."""
    provider = _make_ado_provider()
    provider._client._request.return_value = {
        "records": [
            {"type": "Task", "result": "failed", "id": "guid-1", "name": "Build step",
             "parentId": "phase-1", "log": {"id": 7}},
            {"type": "Task", "result": "succeeded", "id": "guid-2", "name": "OK step",
             "parentId": "phase-1", "log": {"id": 8}},
            {"type": "Task", "result": "canceled", "id": "guid-3", "name": "Cascaded step",
             "parentId": "phase-1", "log": {"id": 9}},
            {"type": "Phase", "result": "failed", "id": "guid-4", "name": "Phase 1",
             "parentId": None, "log": {"id": 10}},
            {"type": "Task", "result": "failed", "id": "guid-5", "name": "No log step",
             "parentId": "phase-1", "log": None},
        ]
    }

    jobs = provider.list_failed_jobs("999")

    assert len(jobs) == 1
    job = jobs[0]
    assert job["job_id"] == "999:7"
    assert job["name"] == "Build step"
    assert job["stage"] == "phase-1"
    assert job["web_url"] == (
        "https://dev.azure.com/org/proj/_build/results?buildId=999&view=logs&j=guid-1"
    )


def test_f2_ado_log_value_lines_joined():
    """_request devuelve {"count": 3, "value": ["a","b","c"]} ⇒ get_job_log == "a\\nb\\nc"."""
    provider = _make_ado_provider()
    provider._client._request.return_value = {"count": 3, "value": ["a", "b", "c"]}

    log = provider.get_job_log("999:7")

    assert log == "a\nb\nc"


def test_f2_ado_apierror_translated_status():
    """_request lanza AdoApiError(status_code=404) ⇒ el adapter lanza TrackerApiError con .status == 404."""
    from services.ado_client import AdoApiError

    provider = _make_ado_provider()
    provider._client._request.side_effect = AdoApiError("not found", status_code=404)

    with pytest.raises(TrackerApiError) as exc_info:
        provider.list_failed_jobs("999")

    assert exc_info.value.status == 404


def test_f2_ado_log_composite_id_parsed():
    """job_id 'build:log' se parsea correctamente en la URL."""
    provider = _make_ado_provider()
    provider._client._request.return_value = {"count": 1, "value": ["line1"]}

    provider.get_job_log("999:7")

    called_url = provider._client._request.call_args[0][1]
    assert "builds/999/logs/7" in called_url


def test_f2_ado_bad_id_400():
    """job_id sin ':' ⇒ TrackerApiError(400, ...) antes de llamar a la red."""
    provider = _make_ado_provider()

    with pytest.raises(TrackerApiError) as exc_info:
        provider.get_job_log("no-separator")

    assert exc_info.value.status == 400
    provider._client._request.assert_not_called()


def test_f2_tracker_error_propagates():
    """404 del pipeline ⇒ TrackerApiError."""
    provider = _make_ado_provider()
    from services.ado_client import AdoApiError
    provider._client._request.side_effect = AdoApiError("pipeline not found", status_code=404)

    with pytest.raises(TrackerApiError):
        provider.list_failed_jobs("nonexistent")
