"""Plan 91 F4 — conexión RDP 1-click (POST /api/devops/servers/<alias>/rdp).

Mismos fixtures que F3; monkeypatch de sys.platform y subprocess.run/Popen EN EL
MÓDULO api.devops_servers.
"""
import os
import subprocess

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import services.server_registry as sr
import api.devops_servers as ds


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
    orig = getattr(cfg.config, "STACKY_DEVOPS_SERVERS_ENABLED", False)
    cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = True
    path = tmp_path / "devops_servers.json"
    monkeypatch.setattr(sr, "_registry_path", lambda: path)
    monkeypatch.setattr(sr, "keyring", _FakeKeyring())
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = orig


def _c(app):
    return app.test_client()


def _make_server(app, *, with_password=True, host="myhost", domain="DOM", username="usr"):
    c = _c(app)
    c.post("/api/devops/servers", json={
        "alias": "srv1", "host": host, "domain": domain, "username": username,
        **({"password": "S3cr3t!XYZ"} if with_password else {}),
    })
    return c


def test_f4_non_windows_501(app_on, monkeypatch):
    monkeypatch.setattr(ds.sys, "platform", "linux")
    c = _make_server(app_on)
    r = c.post("/api/devops/servers/srv1/rdp", json={})
    assert r.status_code == 501


def test_f4_unknown_alias_404(app_on, monkeypatch):
    monkeypatch.setattr(ds.sys, "platform", "win32")
    c = _c(app_on)
    r = c.post("/api/devops/servers/nope/rdp", json={})
    assert r.status_code == 404


def test_f4_no_password_409(app_on, monkeypatch):
    monkeypatch.setattr(ds.sys, "platform", "win32")
    c = _make_server(app_on, with_password=False)
    r = c.post("/api/devops/servers/srv1/rdp", json={})
    assert r.status_code == 409


def test_f4_happy_path_calls_cmdkey_then_mstsc(app_on, monkeypatch):
    monkeypatch.setattr(ds.sys, "platform", "win32")
    run_calls = []
    popen_calls = []

    def _fake_run(args, **kw):
        run_calls.append(args)
        class _R:
            returncode = 0
        return _R()

    def _fake_popen(args, **kw):
        popen_calls.append(args)
        return object()

    monkeypatch.setattr(ds.subprocess, "run", _fake_run)
    monkeypatch.setattr(ds.subprocess, "Popen", _fake_popen)
    c = _make_server(app_on)
    r = c.post("/api/devops/servers/srv1/rdp", json={})
    assert r.status_code == 200
    assert run_calls and "/generic:TERMSRV/myhost" in run_calls[0]
    assert any("/user:DOM\\usr" == a for a in run_calls[0])
    assert popen_calls and popen_calls[0] == ["mstsc", "/v:myhost"]


def test_f4_domain_empty_user_arg_plain(app_on, monkeypatch):
    monkeypatch.setattr(ds.sys, "platform", "win32")
    run_calls = []
    monkeypatch.setattr(ds.subprocess, "run", lambda args, **kw: run_calls.append(args) or type("R", (), {"returncode": 0})())
    monkeypatch.setattr(ds.subprocess, "Popen", lambda args, **kw: object())
    c = _make_server(app_on, domain="")
    r = c.post("/api/devops/servers/srv1/rdp", json={})
    assert r.status_code == 200
    assert "/user:usr" in run_calls[0]  # sin backslash


def test_f4_cmdkey_fail_502(app_on, monkeypatch):
    monkeypatch.setattr(ds.sys, "platform", "win32")
    monkeypatch.setattr(ds.subprocess, "run", lambda args, **kw: type("R", (), {"returncode": 1})())
    c = _make_server(app_on)
    r = c.post("/api/devops/servers/srv1/rdp", json={})
    assert r.status_code == 502
    assert "S3cr3t!XYZ" not in r.get_data(as_text=True)


def test_f4_flag_off_404(app_on, monkeypatch):
    import config as cfg
    monkeypatch.setattr(ds.sys, "platform", "win32")
    c = _make_server(app_on)
    cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = False
    try:
        r = c.post("/api/devops/servers/srv1/rdp", json={})
        assert r.status_code == 404
    finally:
        cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = True


def test_f4_cmdkey_timeout_502_no_password_leak(app_on, monkeypatch):
    monkeypatch.setattr(ds.sys, "platform", "win32")

    def _timeout(args, **kw):
        raise subprocess.TimeoutExpired(cmd=["cmdkey", "/pass:S3cr3t!XYZ"], timeout=15)

    monkeypatch.setattr(ds.subprocess, "run", _timeout)
    c = _make_server(app_on)
    r = c.post("/api/devops/servers/srv1/rdp", json={})
    assert r.status_code == 502
    txt = r.get_data(as_text=True)
    assert "S3cr3t!XYZ" not in txt
    assert "cmdkey /generic" not in txt


def test_f4_success_updates_last_connected(app_on, monkeypatch):
    monkeypatch.setattr(ds.sys, "platform", "win32")
    monkeypatch.setattr(ds.subprocess, "run", lambda args, **kw: type("R", (), {"returncode": 0})())
    monkeypatch.setattr(ds.subprocess, "Popen", lambda args, **kw: object())
    c = _make_server(app_on)
    r = c.post("/api/devops/servers/srv1/rdp", json={})
    assert r.status_code == 200
    srv = sr.get_server("srv1")
    assert isinstance(srv["last_connected_at"], str) and srv["last_connected_at"]
    lst = c.get("/api/devops/servers").get_json()
    item = next(s for s in lst["servers"] if s["alias"] == "srv1")
    assert item["last_connected_at"]
