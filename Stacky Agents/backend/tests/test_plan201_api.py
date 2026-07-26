"""Plan 201 F4/F6/F7 — API del Taller de Compilación.

Flag OFF ⇒ 404 en todo. Sin workspace activo ⇒ 200 con catálogo vacío (nunca 500).
Sin toolchain ⇒ 200 con doctor (nunca error).
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import api.devops_build_workshop as bw  # noqa: E402

_TC_OK = {"available": True, "builder": "dotnet", "msbuild_path": None,
          "dotnet_path": "C:\\dotnet.exe", "version": "8.0.404", "remediation": None}
_TC_MISSING = {"available": False, "builder": None, "msbuild_path": None,
               "dotnet_path": None, "version": None,
               "remediation": {"message": "Instalá el SDK", "command": "winget ...",
                               "url": "https://dotnet.microsoft.com/download"}}


@pytest.fixture(scope="module")
def client():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _entorno(tmp_path, monkeypatch):
    from config import config as cfg
    from services import solution_store

    monkeypatch.setattr(cfg, "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED", True, raising=False)
    monkeypatch.setattr(solution_store, "store_path",
                        lambda: tmp_path / "build_solutions.json", raising=True)
    monkeypatch.setattr(bw, "data_dir", lambda: tmp_path, raising=True)
    monkeypatch.setattr(bw, "_active_workspace_root", lambda: tmp_path / "ws", raising=True)
    monkeypatch.setattr(bw, "detect_toolchain", lambda: dict(_TC_OK), raising=True)
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)


def _fake_catalog(monkeypatch, solutions):
    from services import solution_store

    monkeypatch.setattr(
        solution_store, "scan_solutions_ex",
        lambda ws: {"solutions": [dict(s) for s in solutions], "truncated": False},
        raising=True,
    )


def _sol(slug, tipos=("web",)):
    return {"slug": slug, "sln_path": f"C:\\ws\\{slug}.sln", "sln_name": slug,
            "friendly_name": slug.title(),
            "projects": [{"name": "p", "csproj_path": "x", "type": t,
                          "target_framework": "net8.0"} for t in tipos]}


# ── F4 ───────────────────────────────────────────────────────────────────────

def test_scan_off_returns_404(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED", False, raising=False)

    assert client.post("/api/devops/build/scan", json={}).status_code == 404
    assert client.get("/api/devops/build/catalog").status_code == 404
    assert client.get("/api/devops/build/doctor").status_code == 404
    assert client.post("/api/devops/build/compile", json={"confirm": True}).status_code == 404


def test_scan_no_active_workspace_returns_empty_200(client, monkeypatch):
    monkeypatch.setattr(bw, "_active_workspace_root", lambda: None, raising=True)

    r = client.post("/api/devops/build/scan", json={})

    assert r.status_code == 200
    body = r.get_json()
    assert body["workspace_root"] is None
    assert body["catalog"]["solutions"] == []
    assert "warning" in body
    assert body["toolchain"]["available"] is True


def test_scan_persists_and_catalog_reads_back(client, monkeypatch):
    _fake_catalog(monkeypatch, [_sol("uno"), _sol("dos", ("library",))])

    scan = client.post("/api/devops/build/scan", json={}).get_json()
    catalog = client.get("/api/devops/build/catalog").get_json()

    assert [s["slug"] for s in scan["catalog"]["solutions"]] == ["uno", "dos"]
    assert catalog["catalog"]["solutions"] == scan["catalog"]["solutions"]
    por_slug = {s["slug"]: s["tracked"] for s in catalog["catalog"]["solutions"]}
    assert por_slug == {"uno": True, "dos": False}, "solo lo desplegable nace tildado"


def test_track_toggles(client, monkeypatch):
    _fake_catalog(monkeypatch, [_sol("uno")])
    client.post("/api/devops/build/scan", json={})

    r = client.post("/api/devops/build/track", json={"slug": "uno", "tracked": False})

    assert r.status_code == 200
    assert r.get_json()["catalog"]["solutions"][0]["tracked"] is False


def test_doctor_returns_toolchain(client, monkeypatch):
    monkeypatch.setattr(bw, "detect_toolchain", lambda: dict(_TC_MISSING), raising=True)

    body = client.get("/api/devops/build/doctor").get_json()

    assert body["toolchain"]["available"] is False
    assert body["toolchain"]["remediation"]["command"]


# ── F6 ───────────────────────────────────────────────────────────────────────

def test_compile_requires_confirm(client):
    r = client.post("/api/devops/build/compile", json={"slugs": ["uno"]})

    assert r.status_code == 400
    assert r.get_json()["error"] == "confirm requerido"


def test_compile_sin_slugs_rechaza(client):
    r = client.post("/api/devops/build/compile", json={"confirm": True, "slugs": []})

    assert r.status_code == 400


def test_compile_multi_without_unified_rejected(client, monkeypatch):
    _fake_catalog(monkeypatch, [_sol("uno"), _sol("dos")])
    client.post("/api/devops/build/scan", json={})

    r = client.post("/api/devops/build/compile",
                    json={"confirm": True, "slugs": ["uno", "dos"], "unified": False})

    assert r.status_code == 400
    assert "unificado" in r.get_json()["error"]


def test_compile_slug_no_tildado_rechazado(client, monkeypatch):
    _fake_catalog(monkeypatch, [_sol("lib", ("library",))])
    client.post("/api/devops/build/scan", json={})

    r = client.post("/api/devops/build/compile", json={"confirm": True, "slugs": ["lib"]})

    assert r.status_code == 400
    assert "no tildadas" in r.get_json()["error"]


def test_compile_toolchain_missing_returns_doctor_200(client, monkeypatch):
    _fake_catalog(monkeypatch, [_sol("uno")])
    client.post("/api/devops/build/scan", json={})
    monkeypatch.setattr(bw, "detect_toolchain", lambda: dict(_TC_MISSING), raising=True)

    r = client.post("/api/devops/build/compile", json={"confirm": True, "slugs": ["uno"]})

    assert r.status_code == 200, "el doctor NO es un error HTTP: el front lo renderiza"
    body = r.get_json()
    assert body["status"] == "toolchain_missing"
    assert body["toolchain"]["remediation"]["url"]


def test_compile_starts_build_returns_build_id(client, monkeypatch):
    _fake_catalog(monkeypatch, [_sol("uno")])
    client.post("/api/devops/build/scan", json={})
    llamadas = []
    monkeypatch.setattr(
        bw.solution_builder, "start_build",
        lambda slugs, unified, ws: llamadas.append((slugs, unified, ws)) or "fakeid",
        raising=True,
    )

    r = client.post("/api/devops/build/compile", json={"confirm": True, "slugs": ["uno"]})

    assert r.status_code == 200
    assert r.get_json()["build_id"] == "fakeid"
    assert llamadas[0][0] == ["uno"]
    assert llamadas[0][1] is False


def test_status_unknown_returns_404(client):
    assert client.get("/api/devops/build/status/no-existe").status_code == 404


def test_status_devuelve_sobre(client, monkeypatch):
    monkeypatch.setattr(bw.solution_builder, "get_status", lambda bid: {
        "status": "running", "mode": "single", "slugs": ["uno"], "log": [],
        "error": None, "artifact_ready": False, "summary": None,
    }, raising=True)

    body = client.get("/api/devops/build/status/x").get_json()

    assert body["status"] == "running"
    assert body["summary"] is None, "el summary es null mientras corre"


def test_cancel_requires_confirm(client):
    r = client.post("/api/devops/build/cancel/x", json={})

    assert r.status_code == 400


def test_cancel_ok(client, monkeypatch):
    monkeypatch.setattr(bw.solution_builder, "cancel", lambda bid: True, raising=True)

    assert client.post("/api/devops/build/cancel/x", json={"confirm": True}) \
        .get_json() == {"cancelled": True}


# ── F7 ───────────────────────────────────────────────────────────────────────

def test_download_ready_returns_file(client, monkeypatch, tmp_path):
    artefactos = tmp_path / "build_artifacts" / "uno"
    artefactos.mkdir(parents=True, exist_ok=True)
    zip_path = artefactos / "20260101_000000_abc.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("App.dll", "bits")
    monkeypatch.setattr(bw.solution_builder, "artifact_zip_path",
                        lambda bid: zip_path, raising=True)

    r = client.get("/api/devops/build/artifact/x/download")

    assert r.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(r.data)).namelist() == ["App.dll"]


def test_download_unknown_build_404(client, monkeypatch):
    monkeypatch.setattr(bw.solution_builder, "artifact_zip_path", lambda bid: None,
                        raising=True)

    assert client.get("/api/devops/build/artifact/x/download").status_code == 404


def test_download_path_outside_root_rejected(client, monkeypatch, tmp_path):
    afuera = tmp_path / "afuera.zip"
    afuera.write_bytes(b"PK")
    monkeypatch.setattr(bw.solution_builder, "artifact_zip_path", lambda bid: afuera,
                        raising=True)

    assert client.get("/api/devops/build/artifact/x/download").status_code == 400


def test_download_zip_borrado_404(client, monkeypatch, tmp_path):
    fantasma = tmp_path / "build_artifacts" / "uno" / "ya-no-esta.zip"
    monkeypatch.setattr(bw.solution_builder, "artifact_zip_path", lambda bid: fantasma,
                        raising=True)

    assert client.get("/api/devops/build/artifact/x/download").status_code == 404


def test_blueprint_registrado():
    fuente = (ROOT / "api" / "__init__.py").read_text(encoding="utf-8")

    assert fuente.count("devops_build_workshop_bp") == 2, "import + register"


def test_guard_anti_traversal_presente():
    fuente = (ROOT / "api" / "devops_build_workshop.py").read_text(encoding="utf-8")

    assert "commonpath" in fuente
