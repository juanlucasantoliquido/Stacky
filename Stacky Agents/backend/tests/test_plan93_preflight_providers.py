"""Plan 93 F2 — sub-puerto CIPreflightProvider + adapters ADO/GitLab (tests primero).

Mocks HTTP: monkeypatch del `_request` del cliente correspondiente en su módulo
de ORIGEN (patrón 88 C7). NUNCA red real.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Fábrica get_preflight_provider ──────────────────────────────────────────

def test_f2_factory_resolves_gitlab_and_ado():
    from services.ci_preflight import get_preflight_provider

    class _Ctx:
        tracker_type = "gitlab"

    with patch("services.project_context.resolve_project_context", return_value=_Ctx()):
        with patch("services.gitlab_provider.GitLabClient") as MockClient:
            MockClient.return_value = MagicMock()
            provider = get_preflight_provider("proj")
    assert provider.name == "gitlab"

    class _CtxAdo:
        tracker_type = "azure_devops"

    with patch("services.project_context.resolve_project_context", return_value=_CtxAdo()):
        provider_ado = get_preflight_provider("proj")
    assert provider_ado.name == "azure_devops"


def test_f2_port_structural_conformance():
    from services.ci_preflight import CIPreflightProvider

    class GoodStub:
        name = "test"

        def lint_yaml(self, yaml_str):
            return {}

        def list_runners(self):
            return {}

    class BadStub:
        name = "test"

        def lint_yaml(self, yaml_str):
            return {}

    assert isinstance(GoodStub(), CIPreflightProvider)
    assert not isinstance(BadStub(), CIPreflightProvider)


# ── GitLabPreflightProvider ──────────────────────────────────────────────────

def _make_gitlab_provider():
    from services.gitlab_preflight import GitLabPreflightProvider

    provider = GitLabPreflightProvider.__new__(GitLabPreflightProvider)
    mock_client = MagicMock()
    mock_client._project_path.return_value = "my%2Frepo"
    provider._client = mock_client
    provider._project = "proj"
    return provider, mock_client


def test_f2_gitlab_lint_ok():
    provider, mock_client = _make_gitlab_provider()
    mock_client._request.return_value = ({"valid": True, "errors": []}, {})
    result = provider.lint_yaml("stages: [test]")
    assert result["status"] == "ok"


def test_f2_gitlab_lint_invalid():
    provider, mock_client = _make_gitlab_provider()
    mock_client._request.return_value = (
        {"valid": False, "errors": ["jobs config should contain at least one visible job"]},
        {},
    )
    result = provider.lint_yaml("stages: [test]")
    assert result["status"] == "fail"
    assert "jobs config should contain at least one visible job" in result["errors"]


def test_f2_gitlab_runners_mapped():
    provider, mock_client = _make_gitlab_provider()

    list_body = [
        {"id": 1, "online": True, "status": "online"},
        {"id": 2, "online": False, "status": "offline"},
    ]
    detail_body = {"id": 1, "online": True, "tag_list": ["deploy", "linux"]}

    def _request_side_effect(method, path, **kwargs):
        if path.endswith("/runners") or "/runners?" in path or path.rstrip("/").endswith("runners"):
            return list_body, {}
        if "/runners/1" in path:
            return detail_body, {}
        raise AssertionError(f"llamada inesperada: {method} {path}")

    mock_client._request.side_effect = _request_side_effect
    result = provider.list_runners()
    assert result["status"] == "ok"
    online_runner = next(r for r in result["runners"] if r["id"] == 1)
    assert online_runner["tags"] == ["deploy", "linux"]


def test_f2_gitlab_runner_detail_fail_tags_none():
    provider, mock_client = _make_gitlab_provider()
    list_body = [{"id": 1, "online": True, "status": "online"}]

    def _request_side_effect(method, path, **kwargs):
        if "/runners/1" in path:
            raise RuntimeError("detail falló")
        return list_body, {}

    mock_client._request.side_effect = _request_side_effect
    result = provider.list_runners()
    assert result["status"] == "ok"
    r = result["runners"][0]
    assert r["tags"] is None


def test_f2_gitlab_exception_unavailable():
    provider, mock_client = _make_gitlab_provider()
    mock_client._request.side_effect = RuntimeError("network down")
    result = provider.list_runners()
    assert result["status"] == "unavailable"

    result_lint = provider.lint_yaml("stages: [test]")
    assert result_lint["status"] == "unavailable"


def test_f2_detail_never_leaks_credentials():
    """[C13] el VALOR del token/PAT nunca aparece en el detail, aunque la
    excepción lo traiga embebido en texto (defensa en profundidad)."""
    provider, mock_client = _make_gitlab_provider()
    mock_client._request.side_effect = RuntimeError(
        "HTTP error, headers={'PRIVATE-TOKEN': 'glpat-SECRET1234'}"
    )
    result = provider.list_runners()
    assert result["status"] == "unavailable"
    assert "glpat-SECRET1234" not in str(result)


# ── ado_pipeline_definitions.find_yaml_definition ───────────────────────────

def test_f2_find_definition_matches_yaml_filename():
    from services.ado_pipeline_definitions import find_yaml_definition

    fake_client = MagicMock()
    fake_client._request.return_value = {
        "value": [
            {"id": 7, "name": "deploy", "process": {"yamlFilename": "azure-pipelines.yml"}},
            {"id": 8, "name": "other", "process": {"yamlFilename": "other.yml"}},
        ]
    }
    with patch("services.ado_client.AdoClient", return_value=fake_client):
        result = find_yaml_definition("proj")
    assert result == {"id": 7, "name": "deploy"}


def test_f2_find_definition_error_returns_none():
    from services.ado_pipeline_definitions import find_yaml_definition

    fake_client = MagicMock()
    fake_client._request.side_effect = RuntimeError("boom")
    with patch("services.ado_client.AdoClient", return_value=fake_client):
        result = find_yaml_definition("proj")
    assert result is None


# ── AdoPreflightProvider ──────────────────────────────────────────────────────

def _make_ado_provider():
    from services.ado_preflight import AdoPreflightProvider

    provider = AdoPreflightProvider.__new__(AdoPreflightProvider)
    mock_client = MagicMock()
    mock_client._base_proj = "https://dev.azure.com/org/proj"
    provider._client = mock_client
    provider._project = "proj"
    return provider, mock_client


def test_f2_ado_lint_no_definition_unavailable():
    provider, _mock_client = _make_ado_provider()
    with patch("services.ado_pipeline_definitions.find_yaml_definition", return_value=None):
        result = provider.lint_yaml("stages: []")
    assert result["status"] == "unavailable"
    assert "plan 95" in result["detail"]


def test_f2_ado_lint_preview_ok():
    provider, mock_client = _make_ado_provider()
    mock_client._request.return_value = {"finalYaml": "stages: []"}
    with patch(
        "services.ado_pipeline_definitions.find_yaml_definition",
        return_value={"id": 42, "name": "deploy"},
    ):
        result = provider.lint_yaml("stages: []")
    assert result["status"] == "ok"


def test_f2_ado_lint_preview_yaml_error_fail():
    from services.ado_client import AdoApiError

    provider, mock_client = _make_ado_provider()
    mock_client._request.side_effect = AdoApiError(
        "ADO POST ... -> 400: Unexpected value 'foo'", status_code=400
    )
    with patch(
        "services.ado_pipeline_definitions.find_yaml_definition",
        return_value={"id": 42, "name": "deploy"},
    ):
        result = provider.lint_yaml("stages: []")
    assert result["status"] == "fail"


def test_f2_ado_pools_agents_online():
    provider, mock_client = _make_ado_provider()

    def _request_side_effect(method, url):
        if "distributedtask/pools?" in url:
            return {"value": [{"id": 1, "name": "Default", "isHosted": False}]}
        if "/pools/1/agents" in url:
            return {"value": [{"id": 10, "name": "agent1", "status": "online", "enabled": True}]}
        raise AssertionError(f"llamada inesperada: {method} {url}")

    mock_client._request.side_effect = _request_side_effect
    result = provider.list_runners()
    assert result["status"] == "ok"
    assert any(r["online"] for r in result["runners"])


def test_f2_ado_hosted_pool_ambar():
    provider, mock_client = _make_ado_provider()

    def _request_side_effect(method, url):
        if "distributedtask/pools?" in url:
            return {"value": [{"id": 2, "name": "Azure Pipelines", "isHosted": True}]}
        raise AssertionError(f"llamada inesperada a agents en pool hosted: {method} {url}")

    mock_client._request.side_effect = _request_side_effect
    result = provider.list_runners()
    assert result["status"] == "ok"
    hosted = next(r for r in result["runners"] if "hosted" in (r.get("tags") or []))
    assert hosted["online"] is True
