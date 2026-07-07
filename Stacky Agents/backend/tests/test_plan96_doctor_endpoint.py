"""
Plan 96 F3 — Endpoint POST /api/devops/doctor/diagnose (solo-lectura).
Orquesta F1 (failure_doctor) + F2 (ci_logs_provider); nunca 500 salvo catch-all;
nunca persiste logs.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.tracker_provider import TrackerApiError, TrackerConfigError


@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_DOCTOR_ENABLED", False)
    cfg.config.STACKY_DEVOPS_DOCTOR_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_DOCTOR_ENABLED = original


@pytest.fixture
def app_flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_DOCTOR_ENABLED", False)
    cfg.config.STACKY_DEVOPS_DOCTOR_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_DOCTOR_ENABLED = original


def _post(client, **body):
    return client.post("/api/devops/doctor/diagnose", json=body)


def test_f3_flag_off_404(app_flag_off):
    client = app_flag_off.test_client()
    resp = _post(client, project="proj", pipeline_id="1")
    assert resp.status_code == 404


def test_f3_missing_params_400(app_flag_on):
    client = app_flag_on.test_client()
    resp = _post(client, project="proj")  # falta pipeline_id
    assert resp.status_code == 400
    resp2 = _post(client, pipeline_id="1")  # falta project
    assert resp2.status_code == 400


def test_f3_happy_two_failed_jobs_classified(app_flag_on):
    client = app_flag_on.test_client()
    provider = MagicMock()
    provider.name = "gitlab"
    provider.list_failed_jobs.return_value = [
        {"job_id": "1", "name": "build", "stage": "build", "web_url": None},
        {"job_id": "2", "name": "test", "stage": "test", "web_url": None},
    ]
    provider.get_job_log.side_effect = [
        "step 1\nrobocopy: command not found\nstep 2",
        "step 1\ncp: cannot stat 'x': No such file or directory\nstep 2",
    ]
    with patch("services.ci_logs_provider.get_ci_logs_provider", return_value=provider):
        resp = _post(client, project="proj", pipeline_id="55")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["provider"] == "gitlab"
    assert data["no_failures_found"] is False
    assert data["failed_jobs_total"] == 2
    matched_ids_job1 = [m["id"] for m in data["jobs"][0]["diagnosis"]["matches"]]
    matched_ids_job2 = [m["id"] for m in data["jobs"][1]["diagnosis"]["matches"]]
    assert "cmd_not_found" in matched_ids_job1
    assert "file_not_found" in matched_ids_job2


def test_f3_no_failures_flag_true(app_flag_on):
    client = app_flag_on.test_client()
    provider = MagicMock()
    provider.name = "gitlab"
    provider.list_failed_jobs.return_value = []
    with patch("services.ci_logs_provider.get_ci_logs_provider", return_value=provider):
        resp = _post(client, project="proj", pipeline_id="55")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["no_failures_found"] is True
    assert data["jobs"] == []
    assert data["failed_jobs_total"] == 0


def test_f3_one_log_unreachable_partial_result(app_flag_on):
    client = app_flag_on.test_client()
    provider = MagicMock()
    provider.name = "gitlab"
    provider.list_failed_jobs.return_value = [
        {"job_id": "1", "name": "build", "stage": "build", "web_url": None},
        {"job_id": "2", "name": "test", "stage": "test", "web_url": None},
    ]
    provider.get_job_log.side_effect = [
        RuntimeError("log purgado"),
        "step 1\nrobocopy: command not found\nstep 2",
    ]
    with patch("services.ci_logs_provider.get_ci_logs_provider", return_value=provider):
        resp = _post(client, project="proj", pipeline_id="55")

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["jobs"]) == 2
    assert data["jobs"][0]["diagnosis"]["matches"] == []
    assert "no pude bajar el log" in data["jobs"][0]["diagnosis"]["snippet"]
    assert "cmd_not_found" in [m["id"] for m in data["jobs"][1]["diagnosis"]["matches"]]


def test_f3_tracker_error_status_propagated(app_flag_on):
    client = app_flag_on.test_client()
    with patch("services.ci_logs_provider.get_ci_logs_provider",
               side_effect=TrackerApiError(404, "pipeline not found", kind="not_found")):
        resp = _post(client, project="proj", pipeline_id="55")

    assert resp.status_code == 404
    data = resp.get_json()
    assert data["kind"] == "not_found"


def test_f3_tracker_config_error_400(app_flag_on):
    client = app_flag_on.test_client()
    with patch("services.ci_logs_provider.get_ci_logs_provider",
               side_effect=TrackerConfigError("gitlab sin flag")):
        resp = _post(client, project="proj", pipeline_id="55")

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["kind"] == "tracker_config"


def test_f3_readonly_no_writes(app_flag_on):
    """Centinela: el doctor nunca escribe (save_client_profile / commit_file)."""
    client = app_flag_on.test_client()
    provider = MagicMock()
    provider.name = "gitlab"
    provider.list_failed_jobs.return_value = [
        {"job_id": "1", "name": "build", "stage": "build", "web_url": None},
    ]
    provider.get_job_log.return_value = "robocopy: command not found"

    with patch("services.ci_logs_provider.get_ci_logs_provider", return_value=provider), \
         patch("services.client_profile.save_client_profile") as mock_save, \
         patch("services.ado_provider.AdoTrackerProvider.commit_file") as mock_commit_ado, \
         patch("services.gitlab_provider.GitLabTrackerProvider.commit_file") as mock_commit_gl:
        resp = _post(client, project="proj", pipeline_id="55")

    assert resp.status_code == 200
    mock_save.assert_not_called()
    mock_commit_ado.assert_not_called()
    mock_commit_gl.assert_not_called()


def test_f3_health_has_doctor_enabled(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/devops/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["doctor_enabled"] is True


def test_f3_route_registered(app_flag_on):
    """La ruta existe en el blueprint (no es un 404 por url_map, sino por flag)."""
    rules = [str(r) for r in app_flag_on.url_map.iter_rules()]
    assert any("/api/devops/doctor/diagnose" in r for r in rules)


def test_f3_failed_jobs_total_exposed_when_capped(app_flag_on):
    """[C5] 12 fallidos ⇒ len(jobs) == 10 y failed_jobs_total == 12 (cap defensivo honesto)."""
    client = app_flag_on.test_client()
    provider = MagicMock()
    provider.name = "gitlab"
    provider.list_failed_jobs.return_value = [
        {"job_id": str(i), "name": f"job{i}", "stage": "build", "web_url": None}
        for i in range(12)
    ]
    provider.get_job_log.return_value = "some log without known pattern"
    with patch("services.ci_logs_provider.get_ci_logs_provider", return_value=provider):
        resp = _post(client, project="proj", pipeline_id="55")

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["jobs"]) == 10
    assert data["failed_jobs_total"] == 12
