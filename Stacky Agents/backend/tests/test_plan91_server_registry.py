"""Plan 91 F2 — servicio server_registry (persistencia JSON sin password + keyring).

Setup: monkeypatch de _registry_path a tmp + fake keyring in-memory.
"""
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
def reg(tmp_path, monkeypatch):
    path = tmp_path / "devops_servers.json"
    monkeypatch.setattr(sr, "_registry_path", lambda: path)
    fake = _FakeKeyring()
    monkeypatch.setattr(sr, "keyring", fake)
    return fake, path


def test_f2_upsert_and_list_roundtrip(reg):
    sr.upsert_server("bravo", "h2", "DOM", "usr2", "")
    sr.upsert_server("alfa", "h1", "DOM", "usr1", "notas")
    servers = sr.list_servers()
    assert [s["alias"] for s in servers] == ["alfa", "bravo"]  # ordenado por alias
    assert all(s["has_password"] is False for s in servers)


def test_f2_upsert_invalid_alias_raises(reg):
    with pytest.raises(ValueError):
        sr.upsert_server("con espacios", "h", "", "u", "")
    with pytest.raises(ValueError):
        sr.upsert_server("", "h", "", "u", "")


def test_f2_set_password_then_has_password(reg):
    sr.upsert_server("srv1", "h", "DOM", "usr", "")
    sr.set_password("srv1", "S3cr3t!")
    assert sr.has_password("srv1") is True
    assert sr.get_credential("srv1") == ("usr", "DOM", "S3cr3t!")


def test_f2_delete_removes_credential(reg):
    fake, _ = reg
    sr.upsert_server("srv1", "h", "DOM", "usr", "")
    sr.set_password("srv1", "x")
    assert sr.delete_server("srv1") is True
    assert sr.get_server("srv1") is None
    assert (sr.KEYRING_SERVICE, "srv1") not in fake.store


def test_f2_password_never_in_json(reg):
    _, path = reg
    sr.upsert_server("srv1", "h", "DOM", "usr", "")
    sr.set_password("srv1", "S3cr3t!XYZ")
    text = path.read_text(encoding="utf-8")
    assert "password" not in text.lower()
    assert "S3cr3t!XYZ" not in text


def test_f2_keyring_unavailable_raises(reg, monkeypatch):
    monkeypatch.setattr(sr, "keyring", None)
    sr.upsert_server("srv1", "h", "DOM", "usr", "")
    assert sr.keyring_available() is False
    with pytest.raises(RuntimeError):
        sr.set_password("srv1", "x")
    assert sr.get_credential("srv1") is None


def test_f2_corrupt_json_returns_empty(reg):
    _, path = reg
    path.write_text("{no-json", encoding="utf-8")
    assert sr.list_servers() == []


def test_f2_cap_100_servers(reg):
    for i in range(sr.MAX_SERVERS):
        sr.upsert_server(f"srv{i:03d}", "h", "", "u", "")
    with pytest.raises(ValueError):
        sr.upsert_server("srv101", "h", "", "u", "")
    # update de uno existente → OK (no cuenta para el cap)
    sr.upsert_server("srv000", "h2", "", "u2", "")


def test_f2_connectivity_dns_fail(reg):
    ok, detail = sr.test_connectivity("host-inexistente-stacky-91.invalid")
    assert ok is False
    assert "DNS" in detail


def test_f2_upsert_invalid_host_raises(reg):
    for bad in ("srv con espacio", "evil /admin", "a/b", ""):
        with pytest.raises(ValueError):
            sr.upsert_server("okalias", bad, "", "u", "")
    for good in ("srv01", "srv01.dominio.local", "10.0.0.5:3390"):
        sr.upsert_server("okalias", good, "", "u", "")  # no raise


def test_f2_delete_without_credential_no_raise(reg):
    sr.upsert_server("srv1", "h", "", "u", "")  # SIN set_password
    assert sr.delete_server("srv1") is True


def test_f2_delete_forgets_termsrv(reg, monkeypatch):
    calls = []

    def _fake_run(args, **kw):
        calls.append(args)
        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(sr.subprocess, "run", _fake_run)
    monkeypatch.setattr(sr.sys, "platform", "win32")
    sr.upsert_server("srv1", "myhost", "", "u", "")
    sr.delete_server("srv1")
    assert any(a == ["cmdkey", "/delete:TERMSRV/myhost"] for a in calls)

    # linux → NO invoca cmdkey
    calls.clear()
    monkeypatch.setattr(sr.sys, "platform", "linux")
    sr.upsert_server("srv2", "otro", "", "u", "")
    sr.delete_server("srv2")
    assert calls == []


def test_f2_clear_password(reg):
    sr.upsert_server("srv1", "h", "DOM", "usr", "")
    sr.set_password("srv1", "x")
    sr.clear_password("srv1")
    assert sr.has_password("srv1") is False
    assert any(s["alias"] == "srv1" for s in sr.list_servers())
