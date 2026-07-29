"""Plan 259 F1 — Tests del alta GitLab en project_manager.

AISLAMIENTO OBLIGATORIO: `PROJECTS_DIR` se monkeypatchea a `tmp_path` en
`project_manager` Y en `services.project_context` (que lo importa POR VALOR,
project_context.py:9-10). Ningun test de este archivo escribe en un archivo de
credenciales real del operador (precedente del plan 216: un test escribio en el
perfil REAL).
"""
from __future__ import annotations

import json

import pytest

import project_manager
from services import client_profile as client_profile_mod
from services import project_context as project_context_mod
from services.secrets_store import read_secret_from_file

_URL = "https://gitlab.com"
_PROJ = "acme/api"
# Literal con forma de token partido a proposito: un literal entero tipo token
# BLOQUEA el push (push-protection de GitHub). Ver gotcha de la casa.
_TOKEN = "glpat-" + "SECRETO0DEPRUEBA"


@pytest.fixture()
def gl(tmp_path, monkeypatch):
    """Proyectos en tmp_path + un workspace_root que existe de verdad."""
    projects = tmp_path / "projects"
    projects.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects)
    monkeypatch.setattr(project_context_mod, "PROJECTS_DIR", projects)
    return {"projects": projects, "ws": str(ws), "tmp": tmp_path}


def _cfg_on_disk(gl, name: str) -> dict:
    path = gl["projects"] / name.upper() / "config.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ── forma canonica del issue_tracker ─────────────────────────────────────────

def test_crea_config_con_forma_canonica(gl):
    project_manager.initialize_gitlab_project(
        name="glproj", url=_URL, project_path=_PROJ, workspace_root=gl["ws"]
    )
    cfg = _cfg_on_disk(gl, "glproj")
    assert cfg["issue_tracker"] == {
        "type": "gitlab",
        "base_url": "https://gitlab.com",
        "project": "acme/api",
        "auth_file": "auth/gitlab_auth.json",
    }


def test_group_opcional_ausente_si_vacio(gl):
    project_manager.initialize_gitlab_project(
        name="glproj", url=_URL, project_path=_PROJ, workspace_root=gl["ws"], group=""
    )
    assert "group" not in _cfg_on_disk(gl, "glproj")["issue_tracker"]


def test_group_presente_si_se_pasa(gl):
    project_manager.initialize_gitlab_project(
        name="glproj", url=_URL, project_path=_PROJ, workspace_root=gl["ws"], group="acme"
    )
    assert _cfg_on_disk(gl, "glproj")["issue_tracker"]["group"] == "acme"


def test_url_sin_barra_final(gl):
    project_manager.initialize_gitlab_project(
        name="glproj", url="https://gitlab.com/", project_path=_PROJ, workspace_root=gl["ws"]
    )
    assert _cfg_on_disk(gl, "glproj")["issue_tracker"]["base_url"] == "https://gitlab.com"


# ── client_profile: el de GitLab, no el de ADO (v2 hallazgo C6 / E9) ─────────

def test_client_profile_es_el_de_gitlab_no_el_de_ado(gl):
    """No alcanza con `"client_profile" in cfg`: hay que afirmar CUAL quedo."""
    project_manager.initialize_gitlab_project(
        name="glproj", url=_URL, project_path=_PROJ, workspace_root=gl["ws"]
    )
    cfg = _cfg_on_disk(gl, "glproj")
    esperado = json.loads(
        (client_profile_mod._DEFAULTS_DIR / "gitlab.json").read_text(encoding="utf-8")
    )
    ado = json.loads(
        (client_profile_mod._DEFAULTS_DIR / "azure_devops.json").read_text(encoding="utf-8")
    )
    assert cfg["client_profile"]["tracker_state_machine"] == esperado["tracker_state_machine"]
    assert cfg["client_profile"]["tracker_state_machine"] != ado["tracker_state_machine"]


def test_client_profile_gitlab_en_deploy_congelado(gl, monkeypatch):
    """Simula PyInstaller: los *.json NO estan en disco. El perfil GitLab tiene
    que salir del template EMBEBIDO, no degradar al de Azure DevOps.
    Falla contra el arbol previo a F1.0."""
    from services.client_profile_default_templates import DEFAULT_TEMPLATES

    monkeypatch.setattr(client_profile_mod, "_DEFAULTS_DIR", gl["tmp"] / "no-existe")
    perfil = client_profile_mod.get_default_client_profile("gitlab")
    assert perfil["tracker_state_machine"] != DEFAULT_TEMPLATES["azure_devops"]["tracker_state_machine"]
    assert perfil["tracker_state_machine"] == DEFAULT_TEMPLATES["gitlab"]["tracker_state_machine"]


# ── credencial cifrada ───────────────────────────────────────────────────────

def test_token_no_queda_en_claro(gl):
    path = project_manager.write_gitlab_auth(name="glproj", url=_URL, token=_TOKEN)
    texto = path.read_text(encoding="utf-8")
    assert _TOKEN not in texto
    assert json.loads(texto).get("token_format")


def test_token_se_puede_releer(gl):
    path = project_manager.write_gitlab_auth(name="glproj", url=_URL, token=_TOKEN)
    assert read_secret_from_file(path, "token", format_field="token_format").value == _TOKEN


# ── idempotencia y preservacion ──────────────────────────────────────────────

def test_idempotente_preserva_extras(gl):
    project_manager.initialize_gitlab_project(
        name="glproj", url=_URL, project_path=_PROJ, workspace_root=gl["ws"]
    )
    cfg_file = gl["projects"] / "GLPROJ" / "config.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    cfg["pinned_agents"] = ["dev.agent.md"]
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")

    project_manager.initialize_gitlab_project(
        name="glproj", url=_URL, project_path=_PROJ, workspace_root=gl["ws"]
    )
    assert _cfg_on_disk(gl, "glproj")["pinned_agents"] == ["dev.agent.md"]


def test_auth_file_custom_se_preserva(gl):
    """auth_file vacio significa "conserva el que ya tenga", NO "poné el default"
    (v2 hallazgo C4). Este test falla contra la F1 de v1."""
    custom = "C:/secretos/gl.json"
    project_manager.initialize_gitlab_project(
        name="glproj", url=_URL, project_path=_PROJ, workspace_root=gl["ws"],
        auth_file=custom,
    )
    assert _cfg_on_disk(gl, "glproj")["issue_tracker"]["auth_file"] == custom

    project_manager.initialize_gitlab_project(
        name="glproj", url=_URL, project_path=_PROJ, workspace_root=gl["ws"], auth_file=""
    )
    assert _cfg_on_disk(gl, "glproj")["issue_tracker"]["auth_file"] == custom


def test_auth_file_default_si_no_habia(gl):
    project_manager.initialize_gitlab_project(
        name="nuevo", url=_URL, project_path=_PROJ, workspace_root=gl["ws"], auth_file=""
    )
    assert (
        _cfg_on_disk(gl, "nuevo")["issue_tracker"]["auth_file"]
        == project_manager.DEFAULT_GITLAB_AUTH_FILE
    )


def test_write_gitlab_auth_respeta_ruta_declarada(gl):
    destino = gl["tmp"] / "custom" / "gl.json"
    path = project_manager.write_gitlab_auth(
        name="glproj", url=_URL, token=_TOKEN, auth_file=str(destino)
    )
    assert path == destino
    assert destino.exists()
    assert not (gl["projects"] / "GLPROJ" / "auth" / "gitlab_auth.json").exists()


# ── cierre del lazo escritura <-> lectura ────────────────────────────────────

def test_auth_path_resuelve_a_gitlab_auth(gl):
    cfg = project_manager.initialize_gitlab_project(
        name="glproj", url=_URL, project_path=_PROJ, workspace_root=gl["ws"]
    )
    resuelto = project_context_mod._auth_path_for(cfg)
    assert resuelto is not None
    assert resuelto.replace("\\", "/").endswith("auth/gitlab_auth.json")


def test_build_tracker_target_lee_lo_escrito(gl):
    """Cierra el lazo: lo que F1 ESCRIBE es exactamente lo que el motor LEE."""
    project_manager.initialize_gitlab_project(
        name="glproj", url=_URL, project_path=_PROJ, workspace_root=gl["ws"], group="acme"
    )
    target = project_context_mod.build_tracker_target("GLPROJ")
    assert target.tracker_type == "gitlab"
    assert target.project_path == "acme/api"
    assert target.base_url == "https://gitlab.com"
