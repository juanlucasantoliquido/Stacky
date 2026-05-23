"""Tests Feature #4 — FlowConfig.

Cubre:
  - CRUD completo (crear, listar, actualizar, borrar).
  - Duplicate state → 409.
  - Validation error (campos faltantes / agent_type inválido) → 400.
  - Update/Delete con id inexistente → 404.
  - Resolve con estado mapeado → {found: true}.
  - Resolve con estado no mapeado → {found: false, agent_type: null}.
  - Fixture con archivo JSON temporal (no toca el real).

Criterios de aceptación cubiertos: CA-4.1, CA-4.5.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_config(tmp_path, monkeypatch):
    """
    Redirige el store a un archivo temporal para que los tests no toquen
    ``data/flow_config.json`` real.
    """
    import services.flow_config_store as store

    tmp_file = tmp_path / "flow_config.json"
    monkeypatch.setattr(store, "_DEFAULT_CONFIG_FILE", tmp_path / "legacy-unused.json")
    monkeypatch.setattr(store, "_CONFIG_FILE", tmp_file)
    yield tmp_file


@pytest.fixture()
def client(tmp_config):
    """Cliente Flask de test con el blueprint registrado."""
    from flask import Flask
    from api.flow_config import bp

    app = Flask(__name__)
    app.register_blueprint(bp, url_prefix="/api/flow-config")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ── helpers ───────────────────────────────────────────────────────────────────

def _post_rule(client, ado_state: str, agent_type: str):
    return client.post(
        "/api/flow-config",
        json={"ado_state": ado_state, "agent_type": agent_type},
    )


# ── Tests: GET /api/flow-config ───────────────────────────────────────────────


class TestListRules:
    def test_empty_returns_ok(self, client):
        resp = client.get("/api/flow-config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["rules"] == []

    def test_lists_created_rule(self, client):
        _post_rule(client, "New", "business")
        resp = client.get("/api/flow-config")
        rules = resp.get_json()["rules"]
        assert len(rules) == 1
        assert rules[0]["ado_state"] == "New"
        assert rules[0]["agent_type"] == "business"


# ── Tests: POST /api/flow-config ──────────────────────────────────────────────


class TestCreateRule:
    def test_create_returns_201(self, client):
        resp = _post_rule(client, "Active", "developer")
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["ok"] is True
        assert body["rule"]["ado_state"] == "Active"
        assert body["rule"]["agent_type"] == "developer"
        assert "id" in body["rule"]
        assert "created_at" in body["rule"]
        assert "updated_at" in body["rule"]

    def test_create_persists_to_file(self, client, tmp_config):
        _post_rule(client, "New", "business")
        raw = json.loads(tmp_config.read_text(encoding="utf-8"))
        assert len(raw["rules"]) == 1
        assert raw["rules"][0]["ado_state"] == "New"

    def test_duplicate_state_returns_409(self, client):
        _post_rule(client, "Active", "developer")
        resp = _post_rule(client, "Active", "qa")
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["ok"] is False
        assert body["error"] == "duplicate_state"
        assert "Active" in body["message"]

    def test_missing_ado_state_returns_400(self, client):
        resp = client.post("/api/flow-config", json={"agent_type": "qa"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["ok"] is False
        assert body["error"] == "validation_error"

    def test_missing_agent_type_returns_400(self, client):
        resp = client.post("/api/flow-config", json={"ado_state": "New"})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "validation_error"

    def test_empty_body_returns_400(self, client):
        resp = client.post("/api/flow-config", json={})
        assert resp.status_code == 400

    def test_invalid_agent_type_returns_400(self, client):
        resp = _post_rule(client, "New", "nonexistent_agent")
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "validation_error"

    def test_create_multiple_states(self, client):
        _post_rule(client, "New", "business")
        _post_rule(client, "Active", "developer")
        resp = client.get("/api/flow-config")
        assert len(resp.get_json()["rules"]) == 2


# ── Tests: PUT /api/flow-config/<rule_id> ────────────────────────────────────


class TestUpdateRule:
    def _create(self, client, ado_state="Active", agent_type="developer") -> str:
        resp = _post_rule(client, ado_state, agent_type)
        return resp.get_json()["rule"]["id"]

    def test_update_returns_200(self, client):
        rule_id = self._create(client)
        resp = client.put(
            f"/api/flow-config/{rule_id}",
            json={"ado_state": "Active", "agent_type": "qa"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["rule"]["agent_type"] == "qa"
        assert body["rule"]["id"] == rule_id

    def test_update_nonexistent_returns_404(self, client):
        resp = client.put(
            "/api/flow-config/no-such-id",
            json={"ado_state": "New", "agent_type": "business"},
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "not_found"

    def test_update_duplicate_state_returns_409(self, client):
        id_a = self._create(client, "New", "business")
        self._create(client, "Active", "developer")
        # Intentar cambiar "New" → "Active" (ya existe)
        resp = client.put(
            f"/api/flow-config/{id_a}",
            json={"ado_state": "Active", "agent_type": "business"},
        )
        assert resp.status_code == 409

    def test_update_same_state_ok(self, client):
        """Actualizar un campo sin cambiar el ado_state no debe dar 409."""
        rule_id = self._create(client)
        resp = client.put(
            f"/api/flow-config/{rule_id}",
            json={"ado_state": "Active", "agent_type": "qa"},
        )
        assert resp.status_code == 200

    def test_update_missing_fields_400(self, client):
        rule_id = self._create(client)
        resp = client.put(f"/api/flow-config/{rule_id}", json={"ado_state": "Active"})
        assert resp.status_code == 400


# ── Tests: DELETE /api/flow-config/<rule_id> ────────────────────────────────


class TestDeleteRule:
    def _create(self, client, ado_state="Active", agent_type="developer") -> str:
        resp = _post_rule(client, ado_state, agent_type)
        return resp.get_json()["rule"]["id"]

    def test_delete_returns_200(self, client):
        rule_id = self._create(client)
        resp = client.delete(f"/api/flow-config/{rule_id}")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_delete_removes_from_list(self, client):
        rule_id = self._create(client)
        client.delete(f"/api/flow-config/{rule_id}")
        rules = client.get("/api/flow-config").get_json()["rules"]
        assert all(r["id"] != rule_id for r in rules)

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/flow-config/no-such-id")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "not_found"

    def test_delete_twice_returns_404(self, client):
        rule_id = self._create(client)
        client.delete(f"/api/flow-config/{rule_id}")
        resp = client.delete(f"/api/flow-config/{rule_id}")
        assert resp.status_code == 404


# ── Tests: GET /api/flow-config/resolve ──────────────────────────────────────


class TestResolve:
    def test_resolve_mapped_state(self, client):
        _post_rule(client, "Active", "developer")
        resp = client.get("/api/flow-config/resolve?ado_state=Active")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["found"] is True
        assert body["ado_state"] == "Active"
        assert body["agent_type"] == "developer"

    def test_resolve_unmapped_state(self, client):
        resp = client.get("/api/flow-config/resolve?ado_state=In+Review")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["found"] is False
        assert body["agent_type"] is None
        assert body["ado_state"] == "In Review"

    def test_resolve_missing_param_returns_400(self, client):
        resp = client.get("/api/flow-config/resolve")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "validation_error"

    def test_resolve_after_delete_returns_not_found(self, client):
        _post_rule(client, "New", "business")
        rules = client.get("/api/flow-config").get_json()["rules"]
        rule_id = rules[0]["id"]
        client.delete(f"/api/flow-config/{rule_id}")
        resp = client.get("/api/flow-config/resolve?ado_state=New")
        assert resp.get_json()["found"] is False

    def test_resolve_multiple_rules_picks_correct(self, client):
        _post_rule(client, "New", "business")
        _post_rule(client, "Active", "developer")
        _post_rule(client, "Code Review", "qa")
        resp = client.get("/api/flow-config/resolve?ado_state=Code+Review")
        body = resp.get_json()
        assert body["found"] is True
        assert body["agent_type"] == "qa"


# ── Tests: store con JSON corrupto ────────────────────────────────────────────


class TestCorruptJsonFallback:
    def test_corrupt_json_falls_back_to_empty(self, tmp_config, monkeypatch):
        """R4 del SDD: JSON inválido → fallback a {rules: []} sin excepción."""
        tmp_config.write_text("INVALID JSON{{{{", encoding="utf-8")

        import services.flow_config_store as store
        monkeypatch.setattr(store, "_CONFIG_FILE", tmp_config)

        rules = store.list_rules()
        assert rules == []


class TestLegacyProjectFallback:
    def test_project_reads_legacy_global_and_migrates_on_write(self, tmp_path, monkeypatch):
        import services.flow_config_store as store

        legacy_file = tmp_path / "data" / "flow_config.json"
        legacy_file.parent.mkdir(parents=True, exist_ok=True)
        legacy_file.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "updated_at": "2026-05-21T00:00:00+00:00",
                    "rules": [
                        {
                            "id": "legacy-rule",
                            "ado_state": "Technical review",
                            "agent_type": "technical",
                            "created_at": "2026-05-21T00:00:00+00:00",
                            "updated_at": "2026-05-21T00:00:00+00:00",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        projects_dir = tmp_path / "projects"
        (projects_dir / "RSPACIFICO").mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(store, "_DEFAULT_CONFIG_FILE", legacy_file)
        monkeypatch.setattr(store, "_CONFIG_FILE", legacy_file)
        monkeypatch.setattr(store, "PROJECTS_DIR", projects_dir)
        monkeypatch.setattr(
            store,
            "get_project_config",
            lambda name: {"name": name} if name == "RSPACIFICO" else None,
        )
        monkeypatch.setattr(store, "get_active_project", lambda: "RSPACIFICO")

        rules = store.list_rules(project_name="RSPACIFICO")
        assert [r["ado_state"] for r in rules] == ["Technical review"]

        created = store.create_rule("Reviewed by Dev", "qa", project_name="RSPACIFICO")
        assert created["ado_state"] == "Reviewed by Dev"

        project_file = projects_dir / "RSPACIFICO" / "flow_config.json"
        raw = json.loads(project_file.read_text(encoding="utf-8"))
        assert [r["ado_state"] for r in raw["rules"]] == [
            "Technical review",
            "Reviewed by Dev",
        ]

    def test_missing_rules_key_falls_back(self, tmp_config, monkeypatch):
        tmp_config.write_text('{"version": "1.0"}', encoding="utf-8")

        import services.flow_config_store as store
        monkeypatch.setattr(store, "_CONFIG_FILE", tmp_config)

        rules = store.list_rules()
        assert rules == []
