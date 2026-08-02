"""Plan 293 — La API del tablero, CABLEADA de verdad.

Este archivo existe por el patron mas caro del repo: codigo construido, testeado,
verde... y jamas cableado. Sin estos casos, todo lo de F1..F12 seria inalcanzable
por HTTP y nadie lo notaria.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    ).stdout or ""


@pytest.fixture()
def cliente():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-b", "principal")
    _git(r, "config", "user.email", "prueba@local")
    _git(r, "config", "user.name", "Prueba")
    (r / "a.txt").write_text("uno\n", encoding="utf-8")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-m", "inicial")
    (r / "a.txt").write_text("dos\n", encoding="utf-8")
    return r


@pytest.fixture()
def con_workspace(monkeypatch, repo):
    """Hace que el proyecto activo apunte al repo temporal Y que la lista blanca
    lo acepte. Nunca se toca el repo de Stacky."""
    from services import console_repo

    class _Ctx:
        workspace_root = str(repo)
        stacky_project_name = "PRUEBA"

    monkeypatch.setattr(
        "services.project_context.resolve_project_context",
        lambda **kw: _Ctx(),
    )
    monkeypatch.setattr(console_repo, "resolve_known_workspace", lambda w: Path(w))
    return repo


# ── El contrato del gate de navegacion ──────────────────────────────────────
def test_01_health_responde_200_incluso_apagado(cliente, monkeypatch):
    from config import config

    monkeypatch.setattr(config, "STACKY_WORKBENCH_ENABLED", False, raising=False)
    r = cliente.get("/api/workbench/health")
    assert r.status_code == 200, "con 404 el tab queda en 'unknown' para siempre"
    assert r.get_json()["flag_enabled"] is False


def test_02_health_usa_la_clave_EXACTA_flag_enabled(cliente):
    """frontend/src/utils/flagHealth.ts:9-16 SOLO acepta `flag_enabled`.
    Con `enabled` el veredicto seria 'unknown' y el enlace directo moriria."""
    cuerpo = cliente.get("/api/workbench/health").get_json()
    assert "flag_enabled" in cuerpo
    assert isinstance(cuerpo["flag_enabled"], bool)


def test_03_la_ruta_NO_esta_duplicada(cliente):
    """Declarar '/api' en el blueprint da /api/api/workbench/... (el defecto que
    hizo rechazar a los planes 72, 73 y 74)."""
    assert cliente.get("/api/workbench/health").status_code == 200
    assert cliente.get("/api/api/workbench/health").status_code == 404


# ── Lectura ─────────────────────────────────────────────────────────────────
def test_04_overview_devuelve_estado_y_semaforo(cliente, con_workspace):
    cuerpo = cliente.get("/api/workbench/overview").get_json()
    assert cuerpo["available"] is True
    assert cuerpo["repo"]["branch"] == "principal"
    assert any(a["path"] == "a.txt" for a in cuerpo["archivos"])
    assert "semaforo" in cuerpo and "bloqueos" in cuerpo["semaforo"]
    assert cuerpo["flags"]["escritura"] is False  # nace apagada


def test_05_overview_apagado_da_404(cliente, monkeypatch):
    from config import config

    monkeypatch.setattr(config, "STACKY_WORKBENCH_ENABLED", False, raising=False)
    r = cliente.get("/api/workbench/overview")
    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"


def test_06_historial_y_ramas_responden(cliente, con_workspace):
    h = cliente.get("/api/workbench/historial?n=5").get_json()
    assert h["available"] is True and h["commits"][0]["asunto"] == "inicial"
    r = cliente.get("/api/workbench/ramas").get_json()
    assert any(x["nombre"] == "principal" and x["actual"] for x in r["ramas"])


def test_07_diff_de_un_archivo(cliente, con_workspace):
    d = cliente.get("/api/workbench/diff?path=a.txt").get_json()
    assert d["available"] is True
    assert "dos" in d["diff"]


def test_08_diff_con_ruta_fuera_del_repo_no_lo_lee(cliente, con_workspace):
    d = cliente.get("/api/workbench/diff?path=../../etc/passwd").get_json()
    assert d["available"] is False


# ── Escritura ───────────────────────────────────────────────────────────────
def test_09_confirmar_sin_confirm_da_400(cliente, con_workspace):
    r = cliente.post("/api/workbench/confirmar", json={"rutas": ["a.txt"], "mensaje": "x"})
    assert r.status_code == 400
    assert r.get_json()["codigo"] == "sin_confirmacion"


def test_10_confirmar_con_la_opcion_apagada_no_guarda(cliente, con_workspace, repo):
    antes = _git(repo, "log", "--format=%s")
    r = cliente.post(
        "/api/workbench/confirmar",
        json={"rutas": ["a.txt"], "mensaje": "x", "confirm": True},
    )
    assert r.get_json()["codigo"] == "escritura_apagada"
    assert _git(repo, "log", "--format=%s") == antes


def test_11_confirmar_guarda_SOLO_lo_elegido(cliente, con_workspace, repo, monkeypatch):
    from config import config

    monkeypatch.setattr(config, "STACKY_WORKBENCH_WRITE_ENABLED", True, raising=False)
    (repo / "ajeno.txt").write_text("de otro\n", encoding="utf-8")
    _git(repo, "add", "-A")  # la sesion paralela

    r = cliente.post(
        "/api/workbench/confirmar",
        json={"rutas": ["a.txt"], "mensaje": "solo a", "confirm": True},
    )
    assert r.get_json()["ok"] is True, r.get_json()
    entraron = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert entraron == ["a.txt"], f"entro trabajo ajeno: {entraron}"


def test_12_demasiados_archivos_se_rechaza(cliente, con_workspace):
    r = cliente.post(
        "/api/workbench/confirmar",
        json={"rutas": [f"f{i}.txt" for i in range(61)], "mensaje": "x", "confirm": True},
    )
    assert r.status_code == 400
    assert r.get_json()["codigo"] == "demasiados_archivos"


def test_13_enviar_y_rama_exigen_confirmacion(cliente, con_workspace):
    for ruta in ("/api/workbench/enviar", "/api/workbench/traer", "/api/workbench/rama"):
        assert cliente.post(ruta, json={}).status_code == 400, ruta


def test_14_rama_con_la_opcion_apagada_no_cambia_nada(cliente, con_workspace, repo):
    r = cliente.post(
        "/api/workbench/rama",
        json={"nombre": "nueva", "crear": True, "confirm": True},
    )
    assert r.get_json()["codigo"] == "escritura_apagada"
    assert "principal" in _git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def test_15_carpeta_no_habilitada_no_se_toca(cliente, monkeypatch, repo):
    """El control de acceso real de Stacky: la lista blanca de carpetas."""
    from services import console_repo

    class _Ctx:
        workspace_root = str(repo)
        stacky_project_name = "PRUEBA"

    monkeypatch.setattr("services.project_context.resolve_project_context", lambda **kw: _Ctx())
    monkeypatch.setattr(console_repo, "resolve_known_workspace", lambda w: None)

    cuerpo = cliente.get("/api/workbench/overview").get_json()
    assert cuerpo["available"] is False
    assert "habilitada" in cuerpo["reason"]
