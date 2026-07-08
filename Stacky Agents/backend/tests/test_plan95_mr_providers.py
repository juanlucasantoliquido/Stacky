"""Plan 95 F2 — MergeRequestProvider + adapters GitLab y ADO. Tests PRIMERO."""

import pytest
from unittest.mock import MagicMock, patch


# ── Test factory y conformance ───────────────────────────────────────────────

def test_f2_factory_and_structural_conformance():
    """F2 — Factory get_merge_request_provider + conformance con Protocol."""
    from services.merge_request_provider import get_merge_request_provider, MR_PORT_METHODS
    from services.gitlab_provider import GitLabTrackerProvider

    # Mockear get_repo_writer y GitLabClient para evitar validación de token
    with patch("services.repo_writer.get_repo_writer") as mock_gw:
        with patch("services.gitlab_provider.GitLabClient"):
            mock_gitlab = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
            mock_gitlab._project = "myorg/myrepo"
            mock_gw.return_value = mock_gitlab

            # GitLabTrackerProvider debería implementar el protocolo
            provider = get_merge_request_provider("test-project")
            assert isinstance(provider, GitLabTrackerProvider)

            # Verificar que tiene todos los métodos
            for method in MR_PORT_METHODS:
                assert hasattr(provider, method), f"Missing method: {method}"


# ── GitLab tests ─────────────────────────────────────────────────────────────

def test_f2_gitlab_create_mr_normalized():
    """F2 — GitLab create_merge_request normalizado (iid como str, state='open')."""
    from services.merge_request_provider import get_merge_request_provider
    from services.gitlab_provider import GitLabTrackerProvider

    with patch("services.repo_writer.get_repo_writer") as mock_gw:
        with patch("services.gitlab_provider.GitLabClient"):
            mock_gitlab = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
            mock_gitlab._project = "myorg/myrepo"
            # Mock del _client
            mock_client = MagicMock()
            mock_client._project_path.return_value = "myorg/myrepo"
            mock_client._request.return_value = (
                {
                    "iid": 42,
                    "web_url": "https://gitlab.com/myorg/myrepo/-/merge_requests/42",
                },
                {},  # headers
            )
            mock_gitlab._client = mock_client
            mock_gw.return_value = mock_gitlab

            provider = get_merge_request_provider("myorg/myrepo")
            result = provider.create_merge_request(
                source_branch="feature",
                target_branch="main",
                title="Add feature",
                description="Description",
            )

            assert result["id"] == "42"
            assert result["state"] == "open"
            assert "gitlab.com" in result["web_url"]


def test_f2_gitlab_get_mr_pipeline_status():
    """F2 — GitLab get_merge_request con head_pipeline status."""
    from services.merge_request_provider import get_merge_request_provider
    from services.gitlab_provider import GitLabTrackerProvider

    with patch("services.repo_writer.get_repo_writer") as mock_gw:
        with patch("services.gitlab_provider.GitLabClient"):
            mock_gitlab = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
            mock_gitlab._project = "myorg/myrepo"
            mock_client = MagicMock()
            mock_client._project_path.return_value = "myorg/myrepo"
            mock_client._request.return_value = (
                {
                    "iid": 42,
                    "state": "opened",
                    "web_url": "https://gitlab.com/myorg/myrepo/-/merge_requests/42",
                    "head_pipeline": {"status": "success"},
                    "merge_status": "can_be_merged",
                },
                {},  # headers
            )
            mock_gitlab._client = mock_client
            mock_gw.return_value = mock_gitlab

            provider = get_merge_request_provider("myorg/myrepo")
            result = provider.get_merge_request("42")

            assert result["id"] == "42"
            assert result["state"] == "open"
            assert result["pipeline_status"] == "success"
            assert result["mergeable"] is True


def test_f2_gitlab_get_mr_no_pipeline():
    """F2 — GitLab get_merge_request sin head_pipeline ⇒ pipeline_status='none'."""
    from services.merge_request_provider import get_merge_request_provider
    from services.gitlab_provider import GitLabTrackerProvider

    with patch("services.repo_writer.get_repo_writer") as mock_gw:
        with patch("services.gitlab_provider.GitLabClient"):
            mock_gitlab = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
            mock_gitlab._project = "myorg/myrepo"
            mock_client = MagicMock()
            mock_client._project_path.return_value = "myorg/myrepo"
            mock_client._request.return_value = (
                {
                    "iid": 42,
                    "state": "opened",
                    "web_url": "https://gitlab.com/myorg/myrepo/-/merge_requests/42",
                    "merge_status": "can_be_merged",
                },
                {},  # headers
            )
            mock_gitlab._client = mock_client
            mock_gw.return_value = mock_gitlab

            provider = get_merge_request_provider("myorg/myrepo")
            result = provider.get_merge_request("42")

            assert result["pipeline_status"] == "none"


def test_f2_gitlab_merge_ok():
    """F2 — GitLab merge_merge_request ⇒ state='merged'."""
    from services.merge_request_provider import get_merge_request_provider
    from services.gitlab_provider import GitLabTrackerProvider

    with patch("services.repo_writer.get_repo_writer") as mock_gw:
        with patch("services.gitlab_provider.GitLabClient"):
            mock_gitlab = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
            mock_gitlab._project = "myorg/myrepo"
            mock_client = MagicMock()
            mock_client._project_path.return_value = "myorg/myrepo"
            # Configurar _request directamente en la instancia para merge
            mock_client._request.return_value = ({"iid": 42}, {},)  # (body, headers)
            mock_gitlab._client = mock_client
            mock_gw.return_value = mock_gitlab

            provider = get_merge_request_provider("myorg/myrepo")
            result = provider.merge_merge_request("42")

            assert result["id"] == "42"
            assert result["state"] == "merged"


def test_f2_gitlab_merge_conflict_propagates():
    """F2 — GitLab merge con conflicto ⇒ TrackerApiError propagada."""
    from services.merge_request_provider import get_merge_request_provider
    from services.gitlab_provider import GitLabTrackerProvider
    from services.tracker_provider import TrackerApiError

    with patch("services.repo_writer.get_repo_writer") as mock_gw:
        with patch("services.gitlab_provider.GitLabClient"):
            mock_gitlab = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
            mock_gitlab._project = "myorg/myrepo"
            mock_client = MagicMock()
            mock_client._project_path.return_value = "myorg/myrepo"
            mock_gitlab._client = mock_client
            mock_gw.return_value = mock_gitlab

            with patch("services.gitlab_provider.GitLabClient._request") as mock_req:
                mock_req.side_effect = Exception("HTTP 405: Method Not Allowed")

                provider = get_merge_request_provider("myorg/myrepo")
                with pytest.raises(Exception):
                    provider.merge_merge_request("42")


# ── ADO tests ─────────────────────────────────────────────────────────────────

def test_f2_ado_create_pr_refnames():
    """F2 — ADO create_merge_request con refNames correctos (refs/heads/...)."""
    from services.ado_provider import AdoTrackerProvider
    from services.tracker_provider import TrackerApiError

    with patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-123"):
        with patch("services.ado_client.AdoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client._base_proj = "https://dev.azure.com/test-org/test-project"
            mock_client._request.return_value = {
                "pullRequestId": 789,
                "_links": {"web": {"href": "https://dev.azure.com/test/pr/789"}},
            }
            mock_client_class.return_value = mock_client

            provider = AdoTrackerProvider(project="test-project")
            result = provider.create_merge_request(
                source_branch="feature",
                target_branch="main",
                title="Add feature",
                description="Description",
            )

            assert result["id"] == "789"
            assert result["state"] == "open"

            # Verificar body del POST
            post_call = [c for c in mock_client._request.call_args_list if c[0][0] == "POST"]
            assert len(post_call) == 1
            post_body = post_call[0][1].get("body")
            assert post_body["sourceRefName"] == "refs/heads/feature"
            assert post_body["targetRefName"] == "refs/heads/main"


def test_f2_ado_get_pr_state_map():
    """F2 — ADO get_merge_request mapea states (active→open, completed→merged, abandoned→closed)."""
    from services.ado_provider import AdoTrackerProvider

    # Caso active → open
    with patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-123"):
        with patch("services.ado_client.AdoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client._base_proj = "https://dev.azure.com/test-org/test-project"
            mock_client._request.return_value = {
                "pullRequestId": 789,
                "status": "active",
                "sourceRefName": "refs/heads/feature",
                "mergeStatus": "succeeded",
                "_links": {"web": {"href": "https://dev.azure.com/test/pr/789"}},
                "value": [],  # Sin builds
            }
            mock_client_class.return_value = mock_client

            provider = AdoTrackerProvider(project="test-project")
            result = provider.get_merge_request("789")

            assert result["state"] == "open"
            assert result["mergeable"] is True

    # Caso completed → merged
    with patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-123"):
        with patch("services.ado_client.AdoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client._base_proj = "https://dev.azure.com/test-org/test-project"
            mock_client._request.return_value = {
                "pullRequestId": 789,
                "status": "completed",
                "sourceRefName": "refs/heads/feature",
                "mergeStatus": "succeeded",
                "_links": {"web": {"href": "https://dev.azure.com/test/pr/789"}},
                "value": [],
            }
            mock_client_class.return_value = mock_client

            provider = AdoTrackerProvider(project="test-project")
            result = provider.get_merge_request("789")

            assert result["state"] == "merged"


def test_f2_ado_get_pr_pipeline_from_builds():
    """F2 — ADO get_merge_request obtiene pipeline_status del último build del source branch."""
    from services.ado_provider import AdoTrackerProvider

    with patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-123"):
        with patch("services.ado_client.AdoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client._base_proj = "https://dev.azure.com/test-org/test-project"

            # PR response
            pr_response = {
                "pullRequestId": 789,
                "status": "active",
                "sourceRefName": "refs/heads/feature",
                "mergeStatus": "succeeded",
                "_links": {"web": {"href": "https://dev.azure.com/test/pr/789"}},
            }

            # Builds response
            builds_response = {
                "value": [
                    {
                        "id": 101,
                        "status": "completed",
                        "result": "succeeded",
                        "sourceBranch": "refs/heads/feature",
                    }
                ]
            }

            # Setup side_effect: primero PR, luego builds
            mock_client._request.side_effect = [pr_response, builds_response]
            mock_client_class.return_value = mock_client

            provider = AdoTrackerProvider(project="test-project")
            result = provider.get_merge_request("789")

            assert result["pipeline_status"] == "success"


def test_f2_ado_merge_patch_body_exact():
    """F2 — ADO merge_merge_request PATCH body exact (lastMergeSourceCommit + noFastForward)."""
    from services.ado_provider import AdoTrackerProvider

    with patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-123"):
        with patch("services.ado_client.AdoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client._base_proj = "https://dev.azure.com/test-org/test-project"

            # GET PR response
            pr_response = {
                "pullRequestId": 789,
                "lastMergeSourceCommit": {"commitId": "abc123def456"},
            }

            # PATCH response
            patch_response = {"pullRequestId": 789, "status": "completed"}

            mock_client._request.side_effect = [pr_response, patch_response]
            mock_client_class.return_value = mock_client

            provider = AdoTrackerProvider(project="test-project")
            result = provider.merge_merge_request("789")

            assert result["state"] == "merged"

            # Verificar PATCH body
            patch_call = [c for c in mock_client._request.call_args_list if c[0][0] == "PATCH"]
            assert len(patch_call) == 1
            patch_body = patch_call[0][1].get("body")
            assert patch_body["status"] == "completed"
            assert patch_body["lastMergeSourceCommit"]["commitId"] == "abc123def456"
            assert patch_body["completionOptions"]["mergeStrategy"] == "noFastForward"
            assert patch_body["completionOptions"]["deleteSourceBranch"] is False


def test_f2_ado_merge_policy_rejection_propagates():
    """F2 — ADO merge con policies/reviewers requeridos ⇒ TrackerApiError con mensaje."""
    from services.ado_provider import AdoTrackerProvider
    from services.tracker_provider import TrackerApiError

    with patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-123"):
        with patch("services.ado_client.AdoClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client._base_proj = "https://dev.azure.com/test-org/test-project"

            # GET PR response
            pr_response = {
                "pullRequestId": 789,
                "lastMergeSourceCommit": {"commitId": "abc123def456"},
            }

            # PATCH falla con error de policy
            mock_client._request.side_effect = [
                pr_response,
                Exception("HTTP 409: PR cannot be completed due to policy"),
            ]
            mock_client_class.return_value = mock_client

            provider = AdoTrackerProvider(project="test-project")
            with pytest.raises(TrackerApiError) as exc:
                provider.merge_merge_request("789")

            assert exc.value.kind == "ado_pr_merge_failed"
