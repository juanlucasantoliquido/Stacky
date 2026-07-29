"""Plan 259 F2 — La API crea, actualiza y devuelve proyectos GitLab, y DEJA de
convertirlos a Azure DevOps en silencio.

Cierra un bug de corrupcion de datos VIVO hoy (E2): elegir GitLab en el modal de
Edicion y guardar reescribe `issue_tracker.type` a `azure_devops`.

AISLAMIENTO: PROJECTS_DIR a tmp_path en project_manager Y en api.projects (que lo
importa POR VALOR), y el `.env` de los DOS writers a tmp_path — el alta GitLab
dispara F7, que persiste la perilla del motor.
"""
from __future__ import annotations

import json

import pytest

import project_manager
from services import project_context as project_context_mod

_TOKEN = "glpat-" + "SECRETO0DEPRUEBA"


@pytest.fixture(autouse=True)
def _env_aislado(tmp_path_factory, monkeypatch):
    """NUNCA el .env real del operador: los dos writers redirigidos a tmp."""
    import api.global_config as agc
    import api.harness_flags as ahf
    from config import config as cfg

    env_file = tmp_path_factory.mktemp("env") / ".env"
    env_file.write_text("# env de test\n", encoding="utf-8")
    monkeypatch.setattr(ahf, "_ENV_PATH", env_file)
    monkeypatch.setattr(agc, "_ENV_PATH", env_file)
    monkeypatch.setattr(cfg, "STACKY_GITLAB_ENABLED", False, raising=False)


@pytest.fixture()
def proyectos(tmp_path, monkeypatch):
    import api.projects as api_projects

    projects = tmp_path / "projects"
    projects.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects)
    monkeypatch.setattr(project_context_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(api_projects, "PROJECTS_DIR", projects)
    return {"dir": projects, "ws": str(ws)}


@pytest.fixture()
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def _gl_body(ws: str, name: str = "GLPROJ", **extra) -> dict:
    body = {
        "name": name,
        "workspace_root": ws,
        "tracker_type": "gitlab",
        "gitlab_url": "https://gitlab.com",
        "gitlab_project": "acme/api",
    }
    body.update(extra)
    return body


def _cfg(proyectos, name: str) -> dict:
    return json.loads(
        (proyectos["dir"] / name.upper() / "config.json").read_text(encoding="utf-8")
    )


def _find(resp_json, name: str) -> dict:
    return next(p for p in resp_json["projects"] if p["name"] == name.upper())


# ── alta ─────────────────────────────────────────────────────────────────────

def test_init_gitlab_devuelve_200(proyectos, client):
    resp = client.post("/api/init_project", json=_gl_body(proyectos["ws"]))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["project"]["tracker_type"] == "gitlab"


def test_init_gitlab_escribe_type_gitlab(proyectos, client):
    """ANTI-REGRESION DEL BUG E2: hoy cae al else de azure_devops."""
    client.post("/api/init_project", json=_gl_body(proyectos["ws"]))
    assert _cfg(proyectos, "GLPROJ")["issue_tracker"]["type"] == "gitlab"


def test_init_gitlab_sin_url_400(proyectos, client):
    body = _gl_body(proyectos["ws"])
    del body["gitlab_url"]
    resp = client.post("/api/init_project", json=body)
    assert resp.status_code == 400
    assert "gitlab_url requerida" in resp.get_json()["error"]


def test_init_gitlab_sin_project_400(proyectos, client):
    body = _gl_body(proyectos["ws"])
    del body["gitlab_project"]
    resp = client.post("/api/init_project", json=body)
    assert resp.status_code == 400
    assert "gitlab_project requerido" in resp.get_json()["error"]


def test_init_gitlab_no_exige_organization(proyectos, client):
    """Hoy responde 400 "organization requerida" porque cae al else de ADO."""
    body = _gl_body(proyectos["ws"])
    assert "organization" not in body
    assert client.post("/api/init_project", json=body).status_code == 200


# ── edicion: el bug de corrupcion ────────────────────────────────────────────

def test_patch_a_gitlab_no_degrada_a_ado(proyectos, client):
    """LA PRUEBA DEL BUG: falla contra el arbol actual."""
    client.post("/api/init_project", json={
        "name": "MIGRA", "workspace_root": proyectos["ws"],
        "tracker_type": "azure_devops", "organization": "ACME", "ado_project": "Proj",
    })
    resp = client.patch("/api/projects/MIGRA", json={
        "tracker_type": "gitlab",
        "gitlab_url": "https://gitlab.com",
        "gitlab_project": "acme/api",
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _cfg(proyectos, "MIGRA")["issue_tracker"]["type"] == "gitlab"


def test_patch_parcial_preserva_url(proyectos, client):
    client.post("/api/init_project", json=_gl_body(proyectos["ws"]))
    resp = client.patch("/api/projects/GLPROJ", json={"display_name": "Otro"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    tracker = _cfg(proyectos, "GLPROJ")["issue_tracker"]
    assert tracker["base_url"] == "https://gitlab.com"
    assert tracker["project"] == "acme/api"


# ── listado ──────────────────────────────────────────────────────────────────

def test_listado_expone_campos_gitlab(proyectos, client):
    client.post("/api/init_project", json=_gl_body(proyectos["ws"], gitlab_group="acme"))
    proj = _find(client.get("/api/projects").get_json(), "GLPROJ")
    assert proj["gitlab_url"] == "https://gitlab.com"
    assert proj["gitlab_project"] == "acme/api"
    assert proj["gitlab_group"] == "acme"
    assert proj["gitlab_auth_file"] == "auth/gitlab_auth.json"


def test_listado_no_filtra_gitlab_en_proyecto_ado(proyectos, client):
    client.post("/api/init_project", json={
        "name": "ADOP", "workspace_root": proyectos["ws"],
        "tracker_type": "azure_devops", "organization": "ACME", "ado_project": "Proj",
    })
    proj = _find(client.get("/api/projects").get_json(), "ADOP")
    for key in ("gitlab_url", "gitlab_project", "gitlab_group", "gitlab_auth_file"):
        assert proj[key] == "", f"{key} deberia venir vacio en un proyecto ADO"


def test_listado_no_filtra_ado_project_en_gitlab(proyectos, client):
    """v3 hallazgo B8. `issue_tracker.project` es una clave COMPARTIDA: sin
    condicionar, un proyecto GitLab se lista con ado_project="acme/api",
    EditProjectModal lo semilla incondicionalmente y buildPayload lo reenvia en
    CADA patch. Falla contra el arbol actual: es la prueba de la fuga."""
    client.post("/api/init_project", json=_gl_body(proyectos["ws"]))
    proj = _find(client.get("/api/projects").get_json(), "GLPROJ")
    assert proj["ado_project"] == ""
    assert proj["gitlab_project"] == "acme/api"


def test_listado_conserva_ado_project_en_ado(proyectos, client):
    """No-regresion del Cambio 3-bis."""
    client.post("/api/init_project", json={
        "name": "ADOP", "workspace_root": proyectos["ws"],
        "tracker_type": "azure_devops", "organization": "ACME", "ado_project": "Proj",
    })
    proj = _find(client.get("/api/projects").get_json(), "ADOP")
    assert proj["ado_project"] == "Proj"


def test_has_credentials_gitlab(proyectos, client):
    """Hoy GitLab mira mantis_auth.json."""
    client.post("/api/init_project", json=_gl_body(proyectos["ws"]))
    proj = _find(client.get("/api/projects").get_json(), "GLPROJ")
    assert proj["has_credentials"] is False

    client.post("/api/init_project", json=_gl_body(proyectos["ws"], gitlab_token=_TOKEN))
    proj = _find(client.get("/api/projects").get_json(), "GLPROJ")
    assert (proyectos["dir"] / "GLPROJ" / "auth" / "gitlab_auth.json").exists()
    assert proj["has_credentials"] is True


# ── el token nunca sale ──────────────────────────────────────────────────────

def test_token_nunca_en_la_respuesta(proyectos, client):
    init = client.post("/api/init_project", json=_gl_body(proyectos["ws"], gitlab_token=_TOKEN))
    patch = client.patch("/api/projects/GLPROJ", json={"gitlab_token": _TOKEN})
    listado = client.get("/api/projects")
    creds = client.get("/api/projects/GLPROJ/credentials")

    for etiqueta, resp in (("init", init), ("patch", patch), ("listado", listado), ("creds", creds)):
        assert resp.status_code == 200, f"{etiqueta}: {resp.get_data(as_text=True)}"
        assert _TOKEN not in json.dumps(resp.get_json()), f"el token se filtro en {etiqueta}"
    assert creds.get_json()["gitlab_token_saved"] is True


# ── flag OFF: rechazo EXPLICITO, nunca degradacion silenciosa ────────────────

def test_flag_off_rechaza_explicito(proyectos, client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED", False)
    resp = client.post("/api/init_project", json=_gl_body(proyectos["ws"]))

    assert resp.status_code == 400
    assert "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED" in resp.get_json()["error"]
    assert not (proyectos["dir"] / "GLPROJ" / "config.json").exists(), (
        "con la flag apagada el proyecto NO se debe crear"
    )


# ── no-regresion de los otros 3 trackers (v2, C2: el NameError) ──────────────

def test_alta_ado_jira_mantis_sigue_ok(proyectos, client):
    casos = [
        {"tracker_type": "azure_devops", "organization": "ACME", "ado_project": "Proj"},
        {"tracker_type": "jira", "jira_url": "https://acme.atlassian.net", "jira_key": "ACME"},
        {"tracker_type": "mantis", "mantis_url": "https://mantis.acme", "mantis_project_id": "7"},
    ]
    for i, extra in enumerate(casos):
        body = {"name": f"OTRO{i}", "workspace_root": proyectos["ws"], **extra}
        resp = client.post("/api/init_project", json=body)
        assert resp.status_code == 200, f"{extra['tracker_type']}: {resp.get_data(as_text=True)}"
        assert "gitlab_engine" not in resp.get_json()


# ── auth_file: el operador manda (v2, C4) ────────────────────────────────────

def test_patch_preserva_auth_file_custom(proyectos, client, tmp_path):
    custom = str(tmp_path / "secretos" / "gl.json").replace("\\", "/")
    client.post("/api/init_project", json=_gl_body(proyectos["ws"], gitlab_auth_file=custom))
    assert _cfg(proyectos, "GLPROJ")["issue_tracker"]["auth_file"] == custom

    resp = client.patch("/api/projects/GLPROJ", json={"display_name": "Otro"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _cfg(proyectos, "GLPROJ")["issue_tracker"]["auth_file"] == custom


def test_patch_cambia_auth_file_si_viene_en_el_body(proyectos, client):
    client.post("/api/init_project", json=_gl_body(proyectos["ws"]))
    resp = client.patch("/api/projects/GLPROJ", json={"gitlab_auth_file": "auth/otro.json"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _cfg(proyectos, "GLPROJ")["issue_tracker"]["auth_file"] == "auth/otro.json"
