"""Tests de api.client_profile — endpoints HTTP (plan 16, Fase 1).

Cubren GET / PUT / DELETE de `/api/projects/<name>/client-profile`,
`GET /api/client-profile/default` y `POST|GET /api/projects/<name>/db-readonly-auth`.

Diseño:
  - PROJECTS_DIR se redirige a `tmp_path` via `STACKY_PROJECTS_DIR` (env var),
    y se monkey-patchea el atributo módulo `project_manager.PROJECTS_DIR` que
    los endpoints consultan directamente.
  - La encriptación DPAPI es nativa de Windows (entorno del runner) — no se
    mockea: el campo `password` debe estar presente en el JSON resultante.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Fixture que redirige PROJECTS_DIR / projects_dir a `tmp_path` mediante
    monkey-patch sobre los módulos ya importados (sin tocar sys.modules).

    Cada test tiene su propio tmp_path → aislamiento total. Los proyectos demo
    RSPACIFICO (ADO) y B2IMPACT (Jira) se crean en disco con `config.json`.
    """
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    # Importar (o usar cache) y monkey-patchear TODOS los puntos que leen
    # PROJECTS_DIR / projects_dir. La clave es que estos parches se aplican
    # al módulo que el blueprint ya tiene registrado en sys.modules.
    from app import create_app  # noqa: E402
    import project_manager  # noqa: E402
    import services.client_profile as cp  # noqa: E402
    import api.client_profile as api_cp  # noqa: E402

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cp, "projects_dir", lambda: projects_dir)
    monkeypatch.setattr(api_cp, "PROJECTS_DIR", projects_dir)

    # Crear dos proyectos demo (uno ADO, uno Jira) para los tests cross-tracker.
    for name, tracker_type in [("RSPACIFICO", "azure_devops"), ("B2IMPACT", "jira")]:
        pdir = projects_dir / name
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "config.json").write_text(json.dumps({
            "name": name,
            "display_name": name,
            "issue_tracker": {"type": tracker_type},
        }, indent=2), encoding="utf-8")

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


# ── GET /api/client-profile/default ──────────────────────────────────────────

def test_get_default_template_ado(client):
    r = client.get("/api/client-profile/default?tracker_type=azure_devops")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["tracker_type"] == "azure_devops"
    assert body["template"]["language"]["primary"] == "csharp"


def test_get_default_template_jira(client):
    r = client.get("/api/client-profile/default?tracker_type=jira")
    assert r.status_code == 200
    body = r.get_json()
    assert body["template"]["database"]["type"] == "postgres"


def test_get_default_template_unknown_falls_back(client):
    r = client.get("/api/client-profile/default?tracker_type=zzz")
    assert r.status_code == 200
    # Fallback es azure_devops.
    assert r.get_json()["template"]["language"]["primary"] == "csharp"


# ── GET /api/projects/<name>/client-profile ──────────────────────────────────

def test_get_profile_unknown_project_returns_404(client):
    r = client.get("/api/projects/GHOST/client-profile")
    assert r.status_code == 404
    assert r.get_json()["ok"] is False


def test_get_profile_without_profile_returns_template(client):
    r = client.get("/api/projects/RSPACIFICO/client-profile")
    assert r.status_code == 200
    body = r.get_json()
    assert body["has_profile"] is False
    assert body["profile"] is None
    assert body["tracker_type"] == "azure_devops"
    assert body["default_template"]["language"]["primary"] == "csharp"


def test_get_profile_after_put_returns_normalized(client):
    profile = {
        "schema_version": 1,
        "code_layout": {"online_path": "trunk/OnLine"},
        "language": {"primary": "csharp"},
        "tracker_state_machine": {
            "functional": {"next_state_ok": "Technical review"},
            "technical": {"next_state_ok": "To Do"},
            "developer": {"next_state_ok": "Reviewed by Dev"},
        },
    }
    put = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    assert put.status_code == 200
    get = client.get("/api/projects/RSPACIFICO/client-profile")
    body = get.get_json()
    assert body["has_profile"] is True
    assert body["profile"]["language"]["primary"] == "csharp"
    assert body["validation"]["ok"] is True


# ── PUT /api/projects/<name>/client-profile ──────────────────────────────────

def test_put_profile_rejects_secrets(client):
    bad = {
        "schema_version": 1,
        "database": {"password": "shouldnt-be-here"},
    }
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": bad})
    assert r.status_code == 400
    assert "password" in r.get_json()["error"]


def test_put_profile_rejects_future_schema(client):
    bad = {"schema_version": 9999}
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": bad})
    assert r.status_code == 400
    assert "schema_version" in r.get_json()["error"]


def test_put_profile_rejects_non_object_body(client):
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": "not-an-object"})
    assert r.status_code == 400


def test_put_profile_unknown_project_returns_404(client):
    r = client.put("/api/projects/GHOST/client-profile", json={"profile": {}})
    assert r.status_code == 404


def test_put_profile_accepts_direct_body_or_wrapped(client):
    """El endpoint acepta tanto {profile: {...}} como {...} directo."""
    profile = {
        "schema_version": 1,
        "code_layout": {"online_path": "src"},
        "language": {"primary": "java"},
        "tracker_state_machine": {
            "functional": {"next_state_ok": "In Progress"},
            "technical": {"next_state_ok": "Ready for Dev"},
            "developer": {"next_state_ok": "Code Review"},
        },
    }
    # Wrapped
    r = client.put("/api/projects/B2IMPACT/client-profile", json={"profile": profile})
    assert r.status_code == 200
    # Direct
    r2 = client.put("/api/projects/B2IMPACT/client-profile", json=profile)
    assert r2.status_code == 200


# ── DELETE /api/projects/<name>/client-profile ───────────────────────────────

def test_delete_profile_when_present(client):
    profile = {
        "schema_version": 1,
        "code_layout": {"online_path": "trunk/OnLine"},
        "language": {"primary": "csharp"},
        "tracker_state_machine": {
            "functional": {"next_state_ok": "Technical review"},
            "technical": {"next_state_ok": "To Do"},
            "developer": {"next_state_ok": "Reviewed by Dev"},
        },
    }
    client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    r = client.delete("/api/projects/RSPACIFICO/client-profile")
    assert r.status_code == 200
    assert r.get_json()["cleared"] is True
    # Idempotente
    r2 = client.delete("/api/projects/RSPACIFICO/client-profile")
    assert r2.get_json()["cleared"] is False


def test_delete_profile_unknown_project_returns_404(client):
    r = client.delete("/api/projects/GHOST/client-profile")
    assert r.status_code == 404


# ── POST /api/projects/<name>/db-readonly-auth ───────────────────────────────

def test_db_readonly_auth_save_writes_encrypted_file(client):
    import api.client_profile as api_cp

    r = client.post("/api/projects/RSPACIFICO/db-readonly-auth", json={
        "server": "aisbddev02.cloud.ais-int.net",
        "database": "Pacifico",
        "user": "RSPACIFICOREAD",
        "password": "secret123",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["auth_file"] == "auth/db_readonly.json"
    assert set(body["saved_fields"]) == {"server", "database", "user"}

    # Verificar contenido del archivo: el password está cifrado (no en claro).
    auth_path = api_cp.PROJECTS_DIR / "RSPACIFICO" / "auth" / "db_readonly.json"
    assert auth_path.exists(), f"Esperaba el archivo en {auth_path}"
    payload = json.loads(auth_path.read_text(encoding="utf-8"))
    assert payload["password"]  # presente
    assert payload["password"] != "secret123"  # cifrado
    assert payload.get("password_format") == "dpapi"


def test_db_readonly_auth_save_rejects_empty_password(client):
    r = client.post("/api/projects/RSPACIFICO/db-readonly-auth", json={"password": "   "})
    assert r.status_code == 400
    assert "password" in r.get_json()["error"].lower()


def test_db_readonly_auth_save_unknown_project_returns_404(client):
    r = client.post("/api/projects/GHOST/db-readonly-auth", json={"password": "x"})
    assert r.status_code == 404


def test_db_readonly_auth_get_meta_no_credentials(client):
    r = client.get("/api/projects/RSPACIFICO/db-readonly-auth")
    assert r.status_code == 200
    body = r.get_json()
    assert body["has_credentials"] is False


def test_db_readonly_auth_get_meta_after_save(client):
    client.post("/api/projects/RSPACIFICO/db-readonly-auth", json={
        "server": "db.local",
        "user": "READER",
        "password": "secret",
    })
    r = client.get("/api/projects/RSPACIFICO/db-readonly-auth")
    body = r.get_json()
    assert body["has_credentials"] is True
    assert body["server"] == "db.local"
    assert body["user"] == "READER"
    # El password NUNCA se expone en el metadata.
    assert "password" not in body
