"""Plan 71 F4 — Tests GitLabCIProvider.

7 casos:
  1. infer_item_pipeline pasa ref correcto al delegate.
  2. status success → overall_progress=1.0.
  3. status running → overall_progress=0.5.
  4. source llm → overall_progress=0.0.
  5. pipelines vacías → overall_progress=0.0.
  6. monitor_pipeline lanza NotImplementedError.
  7. _pipelines_to_result es pura.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_gitlab_delegate(pipelines: list[dict]):
    """Crea un mock de GitLabTrackerProvider con infer_pipeline que retorna pipelines."""
    delegate = MagicMock()
    delegate.infer_pipeline = MagicMock(return_value=pipelines)
    return delegate


# ---------------------------------------------------------------------------
# C1 — infer_item_pipeline pasa ref correcto al delegate
# ---------------------------------------------------------------------------
def test_infer_item_pipeline_passes_ref():
    from services.gitlab_ci_provider import GitLabCIProvider
    from services.ci_provider import ItemRef

    delegate = _make_gitlab_delegate([])
    with patch("services.gitlab_ci_provider.GitLabTrackerProvider", return_value=delegate):
        provider = GitLabCIProvider(project="test_proj")
        ref = ItemRef(item_id="55", tracker_type="gitlab", ref="main")
        provider.infer_item_pipeline(ref)

    delegate.infer_pipeline.assert_called_once_with(ref="main")


# ---------------------------------------------------------------------------
# C2 — status success → overall_progress=1.0
# ---------------------------------------------------------------------------
def test_success_progress_is_1():
    from services.gitlab_ci_provider import GitLabCIProvider
    from services.ci_provider import ItemRef

    pipelines = [{"source": "ci", "status": "success", "ref": "main", "sha": "abc", "web_url": "http://x"}]
    delegate = _make_gitlab_delegate(pipelines)
    with patch("services.gitlab_ci_provider.GitLabTrackerProvider", return_value=delegate):
        provider = GitLabCIProvider(project="test_proj")
        ref = ItemRef(item_id="1", tracker_type="gitlab", ref="main")
        result = provider.infer_item_pipeline(ref)

    assert result.overall_progress == 1.0


# ---------------------------------------------------------------------------
# C3 — status running → overall_progress=0.5
# ---------------------------------------------------------------------------
def test_running_progress_is_05():
    from services.gitlab_ci_provider import GitLabCIProvider
    from services.ci_provider import ItemRef

    pipelines = [{"source": "ci", "status": "running", "ref": "main", "sha": "abc", "web_url": "http://x"}]
    delegate = _make_gitlab_delegate(pipelines)
    with patch("services.gitlab_ci_provider.GitLabTrackerProvider", return_value=delegate):
        provider = GitLabCIProvider(project="test_proj")
        ref = ItemRef(item_id="2", tracker_type="gitlab")
        result = provider.infer_item_pipeline(ref)

    assert result.overall_progress == 0.5


# ---------------------------------------------------------------------------
# C4 — source llm → overall_progress=0.0
# ---------------------------------------------------------------------------
def test_llm_source_progress_is_0():
    from services.gitlab_ci_provider import GitLabCIProvider
    from services.ci_provider import ItemRef

    pipelines = [{"source": "llm", "status": "unknown", "ref": ""}]
    delegate = _make_gitlab_delegate(pipelines)
    with patch("services.gitlab_ci_provider.GitLabTrackerProvider", return_value=delegate):
        provider = GitLabCIProvider(project="test_proj")
        ref = ItemRef(item_id="3", tracker_type="gitlab")
        result = provider.infer_item_pipeline(ref)

    assert result.overall_progress == 0.0


# ---------------------------------------------------------------------------
# C5 — pipelines vacías → overall_progress=0.0
# ---------------------------------------------------------------------------
def test_empty_pipelines_progress_is_0():
    from services.gitlab_ci_provider import GitLabCIProvider
    from services.ci_provider import ItemRef

    delegate = _make_gitlab_delegate([])
    with patch("services.gitlab_ci_provider.GitLabTrackerProvider", return_value=delegate):
        provider = GitLabCIProvider(project="test_proj")
        ref = ItemRef(item_id="4", tracker_type="gitlab")
        result = provider.infer_item_pipeline(ref)

    assert result.overall_progress == 0.0


# ---------------------------------------------------------------------------
# C6 — monitor_pipeline lanza NotImplementedError
# ---------------------------------------------------------------------------
def test_monitor_pipeline_delegates_to_poll(mocker=None):
    """Plan 72 F1: monitor_pipeline YA IMPLEMENTADO (delega a poll_pipeline).
    Antes lanzaba NotImplementedError (placeholder Plan 71); ahora funciona.
    """
    from services.gitlab_ci_provider import GitLabCIProvider
    from unittest.mock import MagicMock

    delegate = _make_gitlab_delegate([])
    delegate.poll_pipeline = MagicMock(return_value={
        "id": "456", "status": "running", "ref": "main", "sha": "abc", "web_url": "http://x",
    })
    with patch("services.gitlab_ci_provider.GitLabTrackerProvider", return_value=delegate):
        provider = GitLabCIProvider(project="test_proj")

    result = provider.monitor_pipeline("456")
    delegate.poll_pipeline.assert_called_once_with("456")
    assert result["status"] == "running"


# ---------------------------------------------------------------------------
# C7 — _pipelines_to_result es pura
# ---------------------------------------------------------------------------
def test_pipelines_to_result_pure():
    from services.gitlab_ci_provider import _pipelines_to_result
    from services.ci_provider import ItemRef, ItemPipelineResult

    pipelines = [{"source": "ci", "status": "success", "ref": "main", "sha": "abc", "web_url": "http://x"}]
    ref = ItemRef(item_id="5", tracker_type="gitlab", ref="main")

    result = _pipelines_to_result(pipelines, ref)

    assert isinstance(result, ItemPipelineResult)
    assert result.overall_progress == 1.0
    assert result.item_ref == ref
