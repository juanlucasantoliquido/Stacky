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


# ── prefilled_profile y path_check (plan 17) ─────────────────────────────────

def test_get_profile_returns_prefilled_profile(client):
    """GET devuelve `prefilled_profile` con secciones no-BD pobladas."""
    r = client.get("/api/projects/RSPACIFICO/client-profile")
    assert r.status_code == 200
    body = r.get_json()
    assert "prefilled_profile" in body
    pf = body["prefilled_profile"]
    # Secciones no-BD presentes y con valores del template ADO.
    assert pf["code_layout"]["online_path"] == "trunk/OnLine"
    assert "language" in pf
    assert "tracker_state_machine" in pf
    # database NO se inyecta desde el template.
    assert "database" not in pf


def test_get_profile_prefilled_does_not_override_saved_value(client):
    """Si el operador guardó una ruta custom, prefilled_profile la respeta."""
    profile = {
        "schema_version": 1,
        "code_layout": {"online_path": "src/custom"},
        "language": {"primary": "csharp"},
        "tracker_state_machine": {
            "functional": {"next_state_ok": "Technical review"},
            "technical": {"next_state_ok": "To Do"},
            "developer": {"next_state_ok": "Reviewed by Dev"},
        },
    }
    client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    r = client.get("/api/projects/RSPACIFICO/client-profile")
    body = r.get_json()
    # La ruta del operador gana sobre el default.
    assert body["prefilled_profile"]["code_layout"]["online_path"] == "src/custom"


def test_get_profile_prefilled_database_from_saved_profile(client):
    """Si el perfil guardado tiene database, prefilled_profile lo conserva."""
    profile = {
        "schema_version": 1,
        "code_layout": {"online_path": "trunk/OnLine"},
        "language": {"primary": "csharp"},
        "tracker_state_machine": {
            "functional": {"next_state_ok": "Technical review"},
            "technical": {"next_state_ok": "To Do"},
            "developer": {"next_state_ok": "Reviewed by Dev"},
        },
        "database": {"connection_kind": "odbc"},
    }
    client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    r = client.get("/api/projects/RSPACIFICO/client-profile")
    body = r.get_json()
    assert body["prefilled_profile"]["database"]["connection_kind"] == "odbc"


def test_get_profile_returns_path_check_field(client):
    """GET devuelve `path_check` (puede ser lista vacía si no hay workspace_root)."""
    r = client.get("/api/projects/RSPACIFICO/client-profile")
    assert r.status_code == 200
    body = r.get_json()
    assert "path_check" in body
    # Sin workspace_root configurado, path_check debe ser lista vacía.
    assert body["path_check"] == []


def test_get_profile_path_check_with_workspace_root(tmp_path, monkeypatch):
    """Con workspace_root configurado, path_check incluye las rutas del layout."""
    import json as _json
    import project_manager
    import services.client_profile as cp_mod
    import api.client_profile as api_cp

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cp_mod, "projects_dir", lambda: projects_dir)
    monkeypatch.setattr(api_cp, "PROJECTS_DIR", projects_dir)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # Crear directorio trunk/OnLine para que exista.
    (workspace / "trunk" / "OnLine").mkdir(parents=True)

    pdir = projects_dir / "PROJ"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "config.json").write_text(_json.dumps({
        "name": "PROJ",
        "issue_tracker": {"type": "azure_devops"},
        "workspace_root": str(workspace).replace("\\", "/"),
    }), encoding="utf-8")

    from app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        r = c.get("/api/projects/PROJ/client-profile")
    body = r.get_json()
    assert "path_check" in body
    checks = {f"{e['section']}.{e['key']}": e for e in body["path_check"]}
    # trunk/OnLine existe → exists=True
    assert checks["code_layout.online_path"]["exists"] is True
    # trunk/Batch no existe → exists=False
    assert checks["code_layout.batch_path"]["exists"] is False


def test_get_profile_regression_existing_fields_intact(client):
    """Regresión: profile, default_template, has_profile, validation siguen presentes."""
    r = client.get("/api/projects/RSPACIFICO/client-profile")
    body = r.get_json()
    assert "profile" in body
    assert "default_template" in body
    assert "has_profile" in body
    assert "tracker_type" in body
    # validation solo se incluye cuando has_profile es True.
    assert "validation" in body


# ── Plan 45 F5 — validación de process_catalog[*].kind en PUT ─────────────────

def test_put_accepts_valid_process_catalog(client):
    profile = {
        "schema_version": 1,
        "process_catalog": [
            {"name": "Mul2Bane", "kind": "entry", "purpose": "Convierte lotes"},
            {"name": "RSCore", "kind": "processing", "purpose": "Aplica reglas"},
            {"name": "RsExtrae", "kind": "output", "purpose": "Genera salida"},
        ],
    }
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    assert r.status_code == 200, r.get_json()


def test_put_rejects_invalid_process_kind(client):
    profile = {
        "schema_version": 1,
        "process_catalog": [{"name": "X", "kind": "wololo", "purpose": "p"}],
    }
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "invalid_process_kind"
    assert body["value"] == "wololo"


def test_put_migrates_legacy_spanish_kinds(client):
    """Perfiles pre-plan-45 con kinds en español (plan 42) se migran en el PUT
    en vez de romper el guardado (bug: catálogo legacy bloqueaba guardar presets)."""
    profile = {
        "schema_version": 1,
        "process_catalog": [
            {"name": "Mul2Bane", "kind": "carga", "purpose": "Punto de entrada de la carga"},
            {"name": "RSCore", "kind": "calculo", "purpose": "Aplica reglas"},
            {"name": "RsCierre", "kind": "cierre", "purpose": "Cierra el lote"},
            {"name": "RsExtrae", "kind": "reporte", "purpose": "Genera salida"},
            {"name": "Misc", "kind": "otro", "purpose": "Varios"},
        ],
    }
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    assert r.status_code == 200, r.get_json()
    saved = r.get_json()["profile"]["process_catalog"]
    kinds = [item["kind"] for item in saved]
    assert kinds == ["entry", "processing", "processing", "output", ""]


def test_put_tolerates_empty_kind_during_edit(client):
    """Una fila recién agregada (kind vacío) no debe bloquear el guardado."""
    profile = {
        "schema_version": 1,
        "process_catalog": [{"name": "", "kind": "", "purpose": ""}],
    }
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    assert r.status_code == 200, r.get_json()


def test_put_rejects_non_list_catalog(client):
    profile = {"schema_version": 1, "process_catalog": "nope"}
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    assert r.status_code == 400


# ── GET /api/projects/<name>/process-catalog/autodetect ──────────────────────

def _configure_docs_root(tmp_path: Path) -> Path:
    """Arma un árbol de docs con headings de proceso y apunta RSPACIFICO ahí."""
    docs_root = tmp_path / "docs"
    tech = docs_root / "tecnica"
    tech.mkdir(parents=True, exist_ok=True)
    (tech / "INDEX_MASTER.md").write_text(
        "# Índice\n\n"
        "## El proceso Mul2Bane de carga\n\n"
        "detalle...\n\n"
        "## El proceso RsExtrae de salida\n",
        encoding="utf-8",
    )
    cfg_file = tmp_path / "projects" / "RSPACIFICO" / "config.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    cfg["docs_root"] = str(docs_root)
    cfg_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return docs_root


def test_autodetect_returns_docs_candidates(client, tmp_path):
    _configure_docs_root(tmp_path)
    r = client.get("/api/projects/RSPACIFICO/process-catalog/autodetect")
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["ok"] is True
    names = [c["name"] for c in body["candidates"]]
    assert "El proceso Mul2Bane de carga" in names
    assert "El proceso RsExtrae de salida" in names
    by_name = {c["name"]: c for c in body["candidates"]}
    # Heurística de kind por keywords: "carga" → entry, "salida" → output.
    assert by_name["El proceso Mul2Bane de carga"]["kind"] == "entry"
    assert by_name["El proceso RsExtrae de salida"]["kind"] == "output"
    assert by_name["El proceso Mul2Bane de carga"]["source"] == "docs"
    assert body["counts"]["docs"] == 2


def test_autodetect_excludes_already_cataloged(client, tmp_path):
    _configure_docs_root(tmp_path)
    # Catálogo ya contiene uno de los procesos detectables (case-insensitive).
    profile = {
        "schema_version": 1,
        "process_catalog": [{"name": "el proceso mul2bane de carga", "kind": "entry", "purpose": "p"}],
    }
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    assert r.status_code == 200, r.get_json()
    r = client.get("/api/projects/RSPACIFICO/process-catalog/autodetect")
    assert r.status_code == 200
    names = [c["name"] for c in r.get_json()["candidates"]]
    assert "El proceso Mul2Bane de carga" not in names
    assert "El proceso RsExtrae de salida" in names


def test_autodetect_without_sources_returns_empty_ok(client):
    """Sin docs_root ni épicas: 200 con candidates=[] (nunca rompe)."""
    r = client.get("/api/projects/RSPACIFICO/process-catalog/autodetect")
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["ok"] is True
    assert body["candidates"] == []


def test_autodetect_project_not_found(client):
    r = client.get("/api/projects/NOEXISTE/process-catalog/autodetect")
    assert r.status_code == 404


def test_autodetect_candidates_are_saveable(client, tmp_path):
    """Los candidatos detectados deben pasar la validación del PUT tal cual
    (kind ∈ allowlist o vacío) — cierre del loop detectar → guardar."""
    _configure_docs_root(tmp_path)
    r = client.get("/api/projects/RSPACIFICO/process-catalog/autodetect")
    candidates = r.get_json()["candidates"]
    assert candidates
    profile = {
        "schema_version": 1,
        "process_catalog": [
            {"name": c["name"], "kind": c["kind"], "purpose": c["purpose"]} for c in candidates
        ],
    }
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    assert r.status_code == 200, r.get_json()


# ── Plan 45 F3 — flag issue_from_brief_enabled expuesto al frontend ───────────

def test_frontend_config_exposes_issue_flag(client):
    r = client.get("/api/tickets/config/frontend")
    assert r.status_code == 200
    body = r.get_json()
    assert "issue_from_brief_enabled" in body
    assert isinstance(body["issue_from_brief_enabled"], bool)
