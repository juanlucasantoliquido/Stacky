"""Plan 93 F3 — endpoint POST /api/devops/preflight/check (tests primero).

⚠️ [C3] los imports de la ruta son LAZY: el patch va al módulo de ORIGEN
(services.ci_preflight / services.project_context), NUNCA a api.devops.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


_VALID_SPEC = {
    "name": "pipeline-test",
    "stages": [{
        "name": "build",
        "jobs": [{
            "name": "build-job",
            "steps": [{"name": "compile", "script": "make build"}],
        }],
    }],
}


@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_PREFLIGHT_ENABLED", False)
    cfg.config.STACKY_DEVOPS_PREFLIGHT_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PREFLIGHT_ENABLED = original


@pytest.fixture
def app_flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_PREFLIGHT_ENABLED", False)
    cfg.config.STACKY_DEVOPS_PREFLIGHT_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PREFLIGHT_ENABLED = original


def _fake_provider(name="gitlab", lint=None, runners=None):
    provider = MagicMock()
    provider.name = name
    provider.lint_yaml.return_value = lint or {"status": "ok", "errors": [], "detail": "YAML válido"}
    provider.list_runners.return_value = runners or {
        "status": "ok",
        "runners": [{"id": 1, "online": True, "tags": []}],
        "detail": "",
    }
    return provider


def test_f3_flag_off_404(app_flag_off):
    client = app_flag_off.test_client()
    resp = client.post("/api/devops/preflight/check", json={"project": "p", "spec": _VALID_SPEC})
    assert resp.status_code == 404


def test_f3_missing_params_400(app_flag_on):
    client = app_flag_on.test_client()
    # Sin project
    resp = client.post("/api/devops/preflight/check", json={"spec": _VALID_SPEC})
    assert resp.status_code == 400
    # spec no-dict
    resp = client.post("/api/devops/preflight/check", json={"project": "p", "spec": "no-dict"})
    assert resp.status_code == 400
    # target inválido
    resp = client.post(
        "/api/devops/preflight/check",
        json={"project": "p", "spec": _VALID_SPEC, "target": "invalido"},
    )
    assert resp.status_code == 400


def test_f3_malformed_spec_400_never_500(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.post(
        "/api/devops/preflight/check",
        json={"project": "p", "spec": {"stages": "no-es-lista"}, "target": "gitlab"},
    )
    assert resp.status_code == 400
    assert "spec malformado" in resp.get_json().get("error", "")


def test_f3_target_auto_resolves_tracker(app_flag_on):
    client = app_flag_on.test_client()

    class _Ctx:
        tracker_type = "gitlab"

    fake_provider = _fake_provider(name="gitlab")
    with patch("services.project_context.resolve_project_context", return_value=_Ctx()):
        with patch("services.ci_preflight.get_preflight_provider", return_value=fake_provider):
            resp = client.post(
                "/api/devops/preflight/check",
                json={"project": "p", "spec": _VALID_SPEC},
            )
    assert resp.status_code == 200
    checks = resp.get_json()["checks"]
    ids = [c["id"] for c in checks]
    assert "variables_gitlab" in ids
    assert "variables_ado" not in ids

    # Si resolve_project_context lanza -> fallback "both"
    with patch("services.project_context.resolve_project_context", side_effect=RuntimeError("no ctx")):
        with patch("services.ci_preflight.get_preflight_provider", return_value=fake_provider):
            resp2 = client.post(
                "/api/devops/preflight/check",
                json={"project": "p", "spec": _VALID_SPEC},
            )
    assert resp2.status_code == 200
    ids2 = [c["id"] for c in resp2.get_json()["checks"]]
    assert "variables_gitlab" in ids2
    assert "variables_ado" in ids2


def test_f3_happy_path_gitlab(app_flag_on):
    client = app_flag_on.test_client()
    fake_provider = _fake_provider(name="gitlab")
    with patch("services.ci_preflight.get_preflight_provider", return_value=fake_provider):
        resp = client.post(
            "/api/devops/preflight/check",
            json={"project": "p", "spec": _VALID_SPEC, "target": "gitlab"},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    ids = {c["id"] for c in data["checks"]}
    assert {"estructura", "placeholders", "variables_gitlab", "lint_tracker", "runners"} <= ids
    for check in data["checks"]:
        assert {"id", "status", "title", "detail", "fix_hint"} <= set(check.keys())
    assert "summary" in data


def test_f3_structural_fail_skips_remote(app_flag_on):
    client = app_flag_on.test_client()
    fake_provider = _fake_provider(name="gitlab")
    invalid_spec = {"name": "", "stages": []}
    with patch("services.ci_preflight.get_preflight_provider", return_value=fake_provider) as get_provider:
        resp = client.post(
            "/api/devops/preflight/check",
            json={"project": "p", "spec": invalid_spec, "target": "gitlab"},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    estructura = next(c for c in data["checks"] if c["id"] == "estructura")
    assert estructura["status"] == "fail"
    get_provider.assert_not_called()
    fake_provider.lint_yaml.assert_not_called()


def test_f3_provider_exception_unavailable_never_500(app_flag_on):
    client = app_flag_on.test_client()
    with patch("services.ci_preflight.get_preflight_provider", side_effect=RuntimeError("boom")):
        resp = client.post(
            "/api/devops/preflight/check",
            json={"project": "p", "spec": _VALID_SPEC, "target": "gitlab"},
        )
    assert resp.status_code == 200
    checks = resp.get_json()["checks"]
    tracker_check = next(c for c in checks if c["id"] == "tracker")
    assert tracker_check["status"] == "unavailable"


def test_f3_health_exposes_preflight_enabled(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/devops/health")
    assert resp.status_code == 200
    assert resp.get_json()["preflight_enabled"] is True


def test_f3_readonly_no_writes(app_flag_on):
    client = app_flag_on.test_client()
    fake_provider = _fake_provider(name="gitlab")
    with patch("services.ci_preflight.get_preflight_provider", return_value=fake_provider):
        with patch("services.client_profile.save_client_profile") as mock_save:
            with patch("services.gitlab_provider.GitLabTrackerProvider.commit_file") as mock_commit_gl:
                with patch("services.ado_provider.AdoTrackerProvider.commit_file") as mock_commit_ado:
                    resp = client.post(
                        "/api/devops/preflight/check",
                        json={"project": "p", "spec": _VALID_SPEC, "target": "gitlab"},
                    )
    assert resp.status_code == 200
    mock_save.assert_not_called()
    mock_commit_gl.assert_not_called()
    mock_commit_ado.assert_not_called()


def test_f3_source_scan_readonly_allowlist():
    """[C7] centinela solo-lectura REAL: lee como texto los módulos nuevos del
    plan y asserta que toda ocurrencia de método HTTP mutante esté en una línea
    cuya URL matchee la allowlist dry-run (ci/lint o pipelines/.*/preview)."""
    import re
    from pathlib import Path

    backend_root = Path(__file__).parent.parent
    modules = [
        "services/pipeline_preflight.py",
        "services/ci_preflight.py",
        "services/gitlab_preflight.py",
        "services/ado_preflight.py",
        "services/ado_pipeline_definitions.py",
    ]
    mutating_markers = ('"POST"', ".post(", '"PUT"', ".put(", '"PATCH"', ".patch(", '"DELETE"', ".delete(")
    # DOTALL: la URL suele partirse en varias líneas (f-string multilínea) antes
    # de la llamada _request — pipelines/... y preview pueden quedar separados
    # por saltos de línea dentro de la ventana.
    allowlist_re = re.compile(r"ci/lint|pipelines/.*preview", re.IGNORECASE | re.DOTALL)

    violations = []
    for rel_path in modules:
        content = (backend_root / rel_path).read_text(encoding="utf-8")
        lines = content.splitlines()
        for lineno, line in enumerate(lines, start=1):
            if any(marker in line for marker in mutating_markers):
                # La URL puede estar en la MISMA línea, construida ANTES (hasta 6
                # líneas atrás, típico de un f-string multilínea previo a la
                # llamada _request) o pasada en las 3 líneas siguientes.
                start = max(0, lineno - 7)
                end = min(len(lines), lineno + 3)
                window = "\n".join(lines[start:end])
                if not allowlist_re.search(window):
                    violations.append(f"{rel_path}:{lineno}: {line.strip()}")

    assert violations == [], f"Llamadas mutantes fuera de la allowlist dry-run: {violations}"


def test_f3_route_registered():
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/devops/preflight/check" in rules, (
        f"Ruta /api/devops/preflight/check no registrada. "
        f"Rutas devops: {sorted(r for r in rules if 'devops' in r.lower())}"
    )
