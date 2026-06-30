"""Plan 75 F1 — Tests de las compositoras PURAS de deep links GitLab.

Las compositoras reciben project_path YA URL-encoded (output de _project_path()).
Solo _enc() se aplica sobre iid, sha, group y query (no sobre project_path).
"""
import pytest
from services.gitlab_deep_links import (
    compose_issue_url,
    compose_mr_url,
    compose_commit_url,
    compose_epic_url,
    pipeline_web_url,
    _norm_base,
)


def test_f1_1_compose_issue_url():
    result = compose_issue_url("https://gl.example.com/", "rs%2Fpacifico%2Fstrat", "42")
    assert result == "https://gl.example.com/rs%2Fpacifico%2Fstrat/-/issues/42"


def test_f1_2_compose_mr_url():
    result = compose_mr_url("https://gl.example.com/", "rs%2Fpacifico%2Fstrat", "42")
    assert result == "https://gl.example.com/rs%2Fpacifico%2Fstrat/-/merge_requests/42"


def test_f1_3_compose_commit_url():
    result = compose_commit_url("https://gl.example.com", "rs%2Fpacifico%2Fstrat", "abc123def")
    assert result == "https://gl.example.com/rs%2Fpacifico%2Fstrat/-/commit/abc123def"


def test_f1_4_compose_epic_url():
    result = compose_epic_url("https://gl.example.com", "my-group", "7")
    assert result == "https://gl.example.com/groups/my-group/-/epics/7"


def test_f1_5_norm_base_trailing_slash():
    # base con trailing slash vs sin trailing slash → misma URL final
    r1 = compose_issue_url("https://gl.example.com/", "proj%2Ftest", "1")
    r2 = compose_issue_url("https://gl.example.com", "proj%2Ftest", "1")
    assert r1 == r2


def test_f1_6_no_double_encoding_gate():
    """Gate de significancia C3: project_path ya-encoded no se re-encodea.
    El resultado NO debe contener %25 (doble-encoding ausente)."""
    result = compose_issue_url("https://gl.example.com", "rs%2Fpacifico%2Fstrat", "42")
    assert "%25" not in result, f"Doble-encoding detectado en: {result}"
    assert "rs%2Fpacifico%2Fstrat" in result


def test_f1_7_pipeline_web_url():
    assert pipeline_web_url({"web_url": "https://gl/x"}) == "https://gl/x"
    assert pipeline_web_url({}) is None
    assert pipeline_web_url(None) is None


def test_f1_8_pureza_misma_salida():
    """Pureza: 2 llamadas con mismo input → mismo output."""
    args = ("https://gl.example.com", "rs%2Ftest", "99")
    assert compose_issue_url(*args) == compose_issue_url(*args)
    assert compose_mr_url(*args) == compose_mr_url(*args)
