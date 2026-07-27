"""Plan 215 F5/F6 — API del Publicador de Soluciones."""
from __future__ import annotations

import os

import pytest

_TC_OK = {"available": True, "builder": "dotnet", "dotnet_path": "dotnet",
          "msbuild_path": "msbuild", "version": "8.0"}
_TC_NONE = {"available": False, "builder": None, "dotnet_path": None,
            "msbuild_path": None, "version": None,
            "remediation": {"message": "Instalá el SDK de .NET"}}

_BASE = "/api/devops/solution-publisher"


def _client(enabled: bool = True):
    import config as cfg
    from app import create_app

    cfg.config.STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED = enabled
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def client(monkeypatch, tmp_path):
    import config as cfg
    from services import publish_config_store

    original = getattr(cfg.config, "STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED", False)
    monkeypatch.setattr(publish_config_store, "store_path",
                        lambda: tmp_path / "publish_configs.json")
    yield _client(True)
    cfg.config.STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED = original


def _stub_ws(monkeypatch, ws):
    import api.devops_solution_publisher as mod

    monkeypatch.setattr(mod, "_active_workspace_root", lambda: ws)


def test_endpoints_404_when_flag_off(monkeypatch):
    import config as cfg

    original = getattr(cfg.config, "STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED", False)
    try:
        c = _client(False)
        assert c.get(f"{_BASE}/catalog").status_code == 404
        assert c.post(f"{_BASE}/rescan", json={}).status_code == 404
        assert c.post(f"{_BASE}/run", json={"slug": "x", "confirm": True}).status_code == 404
    finally:
        cfg.config.STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED = original


def test_catalog_no_workspace_returns_empty_200(client, monkeypatch):
    from services import build_toolchain

    _stub_ws(monkeypatch, None)
    monkeypatch.setattr(build_toolchain, "detect_toolchain", lambda: _TC_OK)
    r = client.get(f"{_BASE}/catalog")
    assert r.status_code == 200
    body = r.get_json()
    assert body["workspace_root"] is None
    assert body["catalog"]["solutions"] == []
    assert "warning" in body


def test_catalog_first_open_triggers_scan_once(client, monkeypatch, tmp_path):
    """KPI-1/2: el 1er GET escanea; el 2do NO re-walkea."""
    from services import build_toolchain, solution_store

    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)
    _stub_ws(monkeypatch, ws)
    monkeypatch.setattr(build_toolchain, "detect_toolchain", lambda: _TC_OK)

    calls = {"n": 0}
    state = {"scanned_at": None, "truncated": False, "solutions": []}

    def _fake_rescan(w):
        calls["n"] += 1
        state["scanned_at"] = "2026-07-26T00:00:00Z"
        return state

    monkeypatch.setattr(solution_store, "rescan_preserving_manual", _fake_rescan)
    monkeypatch.setattr(solution_store, "load_catalog", lambda w: dict(state))

    r1 = client.get(f"{_BASE}/catalog")
    assert r1.get_json()["first_scan_ran"] is True
    assert calls["n"] == 1

    r2 = client.get(f"{_BASE}/catalog")
    assert r2.get_json()["first_scan_ran"] is False
    assert calls["n"] == 1, "el 2do GET NO debe re-escanear"


def test_catalog_marks_missing_solutions(client, monkeypatch, tmp_path):
    from services import build_toolchain, solution_store

    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)
    _stub_ws(monkeypatch, ws)
    monkeypatch.setattr(build_toolchain, "detect_toolchain", lambda: _TC_OK)
    monkeypatch.setattr(solution_store, "load_catalog", lambda w: {
        "scanned_at": "ya", "truncated": False,
        "solutions": [{"slug": "s", "sln_path": os.path.join(ws, "borrada.sln"),
                       "friendly_name": "S", "projects": []}],
    })
    body = client.get(f"{_BASE}/catalog").get_json()
    sol = body["catalog"]["solutions"][0]
    assert sol["missing"] is True
    assert sol["origin"] == "scan"
    assert sol["config"]["mode"] == "auto"
    assert "plan" in sol


def test_config_save_validates_and_persists(client, monkeypatch, tmp_path):
    _stub_ws(monkeypatch, str(tmp_path / "ws"))
    ok = client.post(f"{_BASE}/config", json={"slug": "s", "config": {"configuration": "Debug"}})
    assert ok.status_code == 200
    assert ok.get_json()["config"]["configuration"] == "Debug"

    bad = client.post(f"{_BASE}/config",
                      json={"slug": "s", "config": {"extra_args": ["a b; rm"]}})
    assert bad.status_code == 400
    assert "extra_args" in bad.get_json()["error"]

    assert client.post(f"{_BASE}/config", json={}).status_code == 400


def test_run_requires_confirm(client, monkeypatch, tmp_path):
    _stub_ws(monkeypatch, str(tmp_path / "ws"))
    r = client.post(f"{_BASE}/run", json={"slug": "s"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "confirm requerido"


def test_run_toolchain_missing_returns_doctor_200(client, monkeypatch, tmp_path):
    from services import build_toolchain, solution_store

    ws = str(tmp_path / "ws")
    _stub_ws(monkeypatch, ws)
    monkeypatch.setattr(build_toolchain, "detect_toolchain", lambda: _TC_NONE)
    monkeypatch.setattr(solution_store, "load_catalog", lambda w: {
        "solutions": [{"slug": "s", "sln_path": "x.sln", "projects": []}]})
    r = client.post(f"{_BASE}/run", json={"slug": "s", "confirm": True})
    assert r.status_code == 200
    assert r.get_json()["status"] == "toolchain_missing"


def test_run_unsupported_returns_reason_200(client, monkeypatch, tmp_path):
    from services import build_toolchain, publish_profile_scanner, solution_store

    ws = str(tmp_path / "ws")
    _stub_ws(monkeypatch, ws)
    monkeypatch.setattr(build_toolchain, "detect_toolchain", lambda: _TC_OK)
    monkeypatch.setattr(solution_store, "load_catalog", lambda w: {
        "solutions": [{"slug": "s", "sln_path": "x.sln", "projects": []}]})
    monkeypatch.setattr(publish_profile_scanner, "resolve_publish_plan",
                        lambda sol, c, tc: {"mode_effective": "msbuild_pubxml",
                                            "supported": False,
                                            "reason": "sin_pubxml_filesystem",
                                            "target": "", "argv_tail": []})
    r = client.post(f"{_BASE}/run", json={"slug": "s", "confirm": True})
    assert r.status_code == 200
    assert r.get_json()["reason"] == "sin_pubxml_filesystem"


def test_run_starts_and_returns_run_id(client, monkeypatch, tmp_path):
    from services import build_toolchain, publish_profile_scanner, solution_publisher, solution_store

    ws = str(tmp_path / "ws")
    _stub_ws(monkeypatch, ws)
    monkeypatch.setattr(build_toolchain, "detect_toolchain", lambda: _TC_OK)
    monkeypatch.setattr(solution_store, "load_catalog", lambda w: {
        "solutions": [{"slug": "s", "sln_path": "x.sln", "projects": []}]})
    monkeypatch.setattr(publish_profile_scanner, "resolve_publish_plan",
                        lambda sol, c, tc: {"mode_effective": "build_only", "supported": True,
                                            "reason": "", "target": "x.sln", "argv_tail": []})
    monkeypatch.setattr(solution_publisher, "start_publish", lambda slug, w: "RUNID42")
    r = client.post(f"{_BASE}/run", json={"slug": "s", "confirm": True})
    assert r.status_code == 200
    assert r.get_json()["run_id"] == "RUNID42"


def test_status_unknown_run_returns_404(client, monkeypatch, tmp_path):
    _stub_ws(monkeypatch, str(tmp_path / "ws"))
    assert client.get(f"{_BASE}/runs/no-existe/status").status_code == 404


def test_download_guard_rejects_outside_root(client, monkeypatch, tmp_path):
    from services import solution_publisher

    _stub_ws(monkeypatch, str(tmp_path / "ws"))
    afuera = tmp_path / "afuera.zip"
    afuera.write_text("z", encoding="utf-8")
    monkeypatch.setattr(solution_publisher, "artifact_zip_path", lambda rid: afuera)
    assert client.get(f"{_BASE}/runs/r1/artifact/download").status_code == 400


def test_import_valid_and_invalid_paths_mixed(client, monkeypatch, tmp_path):
    from services import build_toolchain, solution_store

    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)
    _stub_ws(monkeypatch, ws)
    monkeypatch.setattr(build_toolchain, "detect_toolchain", lambda: _TC_OK)

    good = os.path.join(ws, "Buena.sln")

    def _fake_add(w, path):
        if not path.endswith(".sln"):
            raise ValueError("La ruta no es un archivo .sln legible")
        return {"scanned_at": None, "truncated": False,
                "solutions": [{"slug": "buena", "sln_path": os.path.normpath(path),
                               "projects": [], "origin": "manual"}]}

    monkeypatch.setattr(solution_store, "add_manual_solution", _fake_add)
    monkeypatch.setattr(solution_store, "load_catalog", lambda w: {
        "scanned_at": None, "truncated": False, "solutions": []})

    r = client.post(f"{_BASE}/solutions/import",
                    json={"paths": [good, os.path.join(ws, "malo.txt")], "confirm": True})
    assert r.status_code == 200
    body = r.get_json()
    assert body["added"] == ["buena"]
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["path"].endswith("malo.txt")

    assert client.post(f"{_BASE}/solutions/import", json={"paths": []}).status_code == 400


def test_deep_scan_reports_new_paths(client, monkeypatch, tmp_path):
    from services import solution_deep_scan, solution_store

    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)
    _stub_ws(monkeypatch, ws)
    conocida = os.path.join(ws, "Ya.sln")
    nueva = os.path.join(ws, "Nueva.sln")
    monkeypatch.setattr(solution_deep_scan, "deep_scan_sln_paths",
                        lambda w, **k: {"paths": [conocida, nueva], "timed_out": False})
    monkeypatch.setattr(solution_store, "load_catalog", lambda w: {
        "solutions": [{"slug": "ya", "sln_path": conocida}]})
    body = client.post(f"{_BASE}/deep-scan", json={}).get_json()
    assert body["new_paths"] == [nueva]
    assert body["timed_out"] is False


def test_all_201_dependent_endpoints_degrade_when_201_absent(client, monkeypatch, tmp_path):
    """C2 — cobertura COMPLETA de la degradación, nunca un 500 por ImportError."""
    import api.devops_solution_publisher as mod

    _stub_ws(monkeypatch, str(tmp_path / "ws"))
    monkeypatch.setattr(mod, "_deps_or_none", lambda: (None, None))

    assert client.get(f"{_BASE}/catalog").get_json()["error"] == "build_workshop_unavailable"
    assert client.post(f"{_BASE}/rescan", json={}).get_json()["error"] == "build_workshop_unavailable"
    assert client.post(f"{_BASE}/run", json={"slug": "s", "confirm": True}).get_json()["error"] \
        == "build_workshop_unavailable"
    assert client.post(f"{_BASE}/solutions/import", json={"paths": [], "confirm": True}) \
        .get_json()["error"] == "build_workshop_unavailable"
    assert client.post(f"{_BASE}/deep-scan", json={}).get_json()["error"] \
        == "build_workshop_unavailable"
    assert client.post(f"{_BASE}/register-deploy-app", json={"run_id": "x", "confirm": True}) \
        .get_json()["error"] == "build_workshop_unavailable"

    # /config y /runs NO dependen del 201 y siguen operativos.
    assert client.post(f"{_BASE}/config", json={"slug": "s", "config": {}}).status_code == 200
    assert client.get(f"{_BASE}/runs").status_code == 200


def test_register_deploy_app_requires_success_run(client, monkeypatch, tmp_path):
    from services import solution_publisher

    _stub_ws(monkeypatch, str(tmp_path / "ws"))
    monkeypatch.setattr(solution_publisher, "get_status",
                        lambda rid: {"status": "failed", "slug": "s"})
    r = client.post(f"{_BASE}/register-deploy-app", json={"run_id": "r1", "confirm": True})
    assert r.status_code == 400
    assert "éxito" in r.get_json()["error"]

    assert client.post(f"{_BASE}/register-deploy-app", json={"run_id": "r1"}).status_code == 400


def test_assist_context_masks_and_404_on_unknown(client, monkeypatch, tmp_path):
    import project_manager
    from services import solution_publisher

    _stub_ws(monkeypatch, str(tmp_path / "ws"))
    assert client.get(f"{_BASE}/runs/fantasma/assist-context").status_code == 404

    tok = "ghp_" + "B" * 36  # partido para no gatillar push-protection
    monkeypatch.setattr(solution_publisher, "get_status", lambda rid: {
        "status": "failed", "slug": "s", "mode_effective": "build_only",
        "argv": ["msbuild", "/p:Password=" + tok], "log": [{"message": "token " + tok}],
        "returncode": 1, "failure_class": None})
    monkeypatch.setattr(project_manager, "get_active_project", lambda: "mi-proyecto")
    body = client.get(f"{_BASE}/runs/r1/assist-context").get_json()
    assert body["project"] == "mi-proyecto"
    assert tok not in body["message"]
    assert "NO ejecutes nada" in body["message"]


def test_assist_context_no_active_project_400(client, monkeypatch, tmp_path):
    import project_manager
    from services import solution_publisher

    _stub_ws(monkeypatch, str(tmp_path / "ws"))
    monkeypatch.setattr(solution_publisher, "get_status",
                        lambda rid: {"status": "failed", "slug": "s", "log": []})
    monkeypatch.setattr(project_manager, "get_active_project", lambda: None)
    r = client.get(f"{_BASE}/runs/r1/assist-context")
    assert r.status_code == 400
    assert r.get_json()["error"] == "sin proyecto activo"


def test_blueprint_registered_once():
    import api

    src = open(api.__file__, encoding="utf-8").read()
    assert src.count("devops_solution_publisher_bp") == 2, "import + register, sin duplicados"
