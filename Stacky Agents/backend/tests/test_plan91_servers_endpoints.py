"""Plan 91 F3 — API /api/devops/servers (CRUD + test conectividad) + health.

Fixtures: espejo de test_plan87_devops_endpoints.py (setear/restaurar la flag) +
monkeypatch de registry path tmp + fake keyring (patrón F2).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import services.server_registry as sr


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, svc, key, val):
        self.store[(svc, key)] = val

    def get_password(self, svc, key):
        return self.store.get((svc, key))

    def delete_password(self, svc, key):
        if (svc, key) not in self.store:
            raise Exception("no existe")
        del self.store[(svc, key)]


@pytest.fixture
def app_on(tmp_path, monkeypatch):
    import config as cfg
    orig_srv = getattr(cfg.config, "STACKY_DEVOPS_SERVERS_ENABLED", False)
    orig_panel = getattr(cfg.config, "STACKY_DEVOPS_PANEL_ENABLED", False)
    cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = True
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = True
    path = tmp_path / "devops_servers.json"
    monkeypatch.setattr(sr, "_registry_path", lambda: path)
    monkeypatch.setattr(sr, "keyring", _FakeKeyring())
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = orig_srv
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = orig_panel


@pytest.fixture
def app_off():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_DEVOPS_SERVERS_ENABLED", False)
    cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = orig


def _c(app):
    return app.test_client()


def test_f3_flag_off_all_routes_404(app_off):
    c = _c(app_off)
    assert c.get("/api/devops/servers").status_code == 404
    assert c.post("/api/devops/servers", json={"alias": "a", "host": "h", "username": "u"}).status_code == 404
    assert c.put("/api/devops/servers/a", json={"host": "h", "username": "u"}).status_code == 404
    assert c.delete("/api/devops/servers/a", json={}).status_code == 404
    assert c.post("/api/devops/servers/a/test", json={}).status_code == 404


def test_f3_health_has_servers_keys(app_off):
    # health SIEMPRE 200 aun con flag del 91 OFF.
    c = _c(app_off)
    r = c.get("/api/devops/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["servers_enabled"] is False
    assert isinstance(body["rdp_available"], bool)


def test_f3_crud_roundtrip(app_on):
    c = _c(app_on)
    r = c.post("/api/devops/servers", json={
        "alias": "srv1", "host": "h1", "domain": "DOM", "username": "usr", "notes": "n", "password": "S3cr3t!",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    lst = c.get("/api/devops/servers").get_json()
    item = next(s for s in lst["servers"] if s["alias"] == "srv1")
    assert item["has_password"] is True
    # PUT cambia notes SIN password → write-only preservado
    r2 = c.put("/api/devops/servers/srv1", json={"host": "h1", "username": "usr", "notes": "nueva"})
    assert r2.status_code == 200
    lst2 = c.get("/api/devops/servers").get_json()
    item2 = next(s for s in lst2["servers"] if s["alias"] == "srv1")
    assert item2["has_password"] is True
    assert item2["notes"] == "nueva"
    # DELETE
    assert c.delete("/api/devops/servers/srv1", json={}).status_code == 200
    assert c.get("/api/devops/servers").get_json()["servers"] == []


def test_f3_post_password_never_in_response(app_on):
    c = _c(app_on)
    r = c.post("/api/devops/servers", json={
        "alias": "srv1", "host": "h", "username": "u", "password": "MyP4ss!Secret",
    })
    assert "MyP4ss!Secret" not in r.get_data(as_text=True)


def test_f3_post_invalid_alias_400(app_on):
    c = _c(app_on)
    r = c.post("/api/devops/servers", json={"alias": "con espacio", "host": "h", "username": "u"})
    assert r.status_code == 400


def test_f3_put_unknown_alias_404(app_on):
    c = _c(app_on)
    r = c.put("/api/devops/servers/nope", json={"host": "h", "username": "u"})
    assert r.status_code == 404


def test_f3_keyring_unavailable_503(app_on, monkeypatch):
    monkeypatch.setattr(sr, "keyring", None)
    c = _c(app_on)
    r = c.post("/api/devops/servers", json={"alias": "srv1", "host": "h", "username": "u", "password": "x"})
    assert r.status_code == 503
    assert "keyring" in r.get_json()["error"].lower()
    # el servidor quedó guardado sin password
    lst = c.get("/api/devops/servers").get_json()
    item = next(s for s in lst["servers"] if s["alias"] == "srv1")
    assert item["has_password"] is False


def test_f3_test_endpoint_returns_ok_detail(app_on, monkeypatch):
    c = _c(app_on)
    c.post("/api/devops/servers", json={"alias": "srv1", "host": "h", "username": "u"})
    monkeypatch.setattr(sr, "test_connectivity", lambda host, **kw: (True, "TCP 3389 OK"))
    r = c.post("/api/devops/servers/srv1/test", json={})
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "detail": "TCP 3389 OK"}


def test_f3_non_json_post_400(app_on):
    c = _c(app_on)
    r = c.post("/api/devops/servers", data="alias=x&host=y", content_type="application/x-www-form-urlencoded")
    assert r.status_code == 400
    r2 = c.post("/api/devops/servers", json={"alias": "srv1", "host": "h", "username": "u"})
    assert r2.status_code != 400


def test_f3_put_password_null_clears(app_on):
    c = _c(app_on)
    c.post("/api/devops/servers", json={"alias": "srv1", "host": "h", "username": "u", "password": "x"})
    # PUT con password: null → borra la credencial
    r = c.put("/api/devops/servers/srv1", json={"host": "h", "username": "u", "password": None})
    assert r.status_code == 200
    lst = c.get("/api/devops/servers").get_json()
    item = next(s for s in lst["servers"] if s["alias"] == "srv1")
    assert item["has_password"] is False
    # PUT SIN el campo password → sigue sin password (no resucita)
    c.put("/api/devops/servers/srv1", json={"host": "h", "username": "u"})
    lst2 = c.get("/api/devops/servers").get_json()
    item2 = next(s for s in lst2["servers"] if s["alias"] == "srv1")
    assert item2["has_password"] is False
