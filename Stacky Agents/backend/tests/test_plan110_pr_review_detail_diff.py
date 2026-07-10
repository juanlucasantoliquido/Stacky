"""Plan 110 F3 — módulo puro de saneo + endpoint /detail con diff saneado."""
import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from services.pr_review_sanitize import redact_secrets, truncate, sanitize_diff


# ── Módulo puro ────────────────────────────────────────────────────────────────
def test_truncate_marks_and_caps():
    text = "x" * 100
    out, truncated = truncate(text, 40)
    assert truncated is True
    assert out.startswith("x" * 40)
    assert "truncado" in out


def test_truncate_zero_means_unlimited():
    text = "y" * 500
    out, truncated = truncate(text, 0)
    assert truncated is False
    assert out == text


def test_redacts_bearer_password_pat_privatekey():
    samples = [
        "Authorization: Bearer abc123DEF._-tok",
        "password = supersecreta",
        "ghp_" + "a" * 30,
        "glpat-" + "b" * 25,
        "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----",
        "https://user:p4ssw0rd@host/repo.git",
    ]
    for s in samples:
        out = redact_secrets(s)
        assert "***REDACTED***" in out, f"no redactó: {s!r}"
    # el prefijo password= se conserva
    assert redact_secrets("password = x").startswith("password")
    assert "supersecreta" not in redact_secrets("password = supersecreta")
    # la contraseña de la URL NO debe filtrarse (endurecimiento de privacidad)
    assert "p4ssw0rd" not in redact_secrets("https://user:p4ssw0rd@host/repo.git")


def test_redacts_email_pii():
    """C1 — un email queda enmascarado y el original no aparece."""
    out = redact_secrets("contacto: juan.perez@empresa.com por dudas")
    assert "juan.perez@empresa.com" not in out
    assert "***REDACTED***" in out


def test_sanitize_diff_redacts_then_truncates():
    text = "ghp_" + "z" * 30 + (" relleno" * 5000)
    out, truncated = sanitize_diff(text, 200)
    assert truncated is True
    assert "ghp_" + "z" * 30 not in out
    assert "***REDACTED***" in out


# ── Endpoint /detail ─────────────────────────────────────────────────────────
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


def _provider_with_diff(diff_text, diff_available=True, note=""):
    provider = mock.MagicMock()
    provider.name = "gitlab"
    provider.get_merge_request.return_value = {
        "id": "7", "state": "open", "pipeline_status": "success", "mergeable": True, "web_url": "u",
    }
    provider.get_merge_request_diff.return_value = {
        "id": "7", "files": [{"path": "a.py", "change_type": "modified"}],
        "diff_text": diff_text, "diff_available": diff_available, "note": note,
    }
    return provider


def test_detail_404_when_flag_off(app_off):
    c = app_off.test_client()
    assert c.get("/api/pr-review/detail?project=p&mr_id=7").status_code == 404


def test_detail_requires_mr_id(app_on):
    c = app_on.test_client()
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider_with_diff("x")):
        assert c.get("/api/pr-review/detail?project=p").status_code == 400


def test_detail_returns_sanitized_diff(app_on):
    c = app_on.test_client()
    secret = "ghp_" + "s" * 30
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider_with_diff(f"token {secret}")):
        resp = c.get("/api/pr-review/detail?project=p&mr_id=7")
        assert resp.status_code == 200
        data = resp.get_json()
        assert secret not in data["diff_text"]
        assert "***REDACTED***" in data["diff_text"]


def test_detail_ado_degraded_note(app_on):
    c = app_on.test_client()
    provider = _provider_with_diff("", diff_available=False, note="ADO: solo archivos")
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=provider):
        resp = c.get("/api/pr-review/detail?project=p&mr_id=7")
        assert resp.status_code == 200
        assert resp.get_json()["diff_available"] is False
        assert resp.get_json()["note"] == "ADO: solo archivos"
