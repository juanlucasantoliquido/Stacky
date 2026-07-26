"""test_plan240_agenda_launcher.py — Plan 240 F2 (cerrado por el Plan 241 F8).

Arranque local ACOTADO de AgendaWeb. Con la flag OFF (default) el comportamiento es
byte-identico al de hoy: BLOCKED/APP_NOT_RUNNING.
"""
import pytest

import agenda_web_launcher as awl
from agenda_web_launcher import ensure_agenda_web, stop_agenda_web

_FLAG = "STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED"
_LOCAL = "http://localhost:35017/AgendaWeb/"


class _PopenSpy:
    def __init__(self):
        self.calls = 0
        self.terminated = 0
        self.pid = 4242

    def __call__(self, *a, **kw):
        self.calls += 1
        return self

    def terminate(self):
        self.terminated += 1

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated += 1


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)
    monkeypatch.delenv("STACKY_DEPLOY_MODE", raising=False)


def test_flag_off_es_no_op(monkeypatch):
    spy = _PopenSpy()
    monkeypatch.setattr(awl.subprocess, "Popen", spy)
    res = ensure_agenda_web(base_url=_LOCAL)
    assert res["ok"] is False
    assert res["code"] == "AUTOSTART_DISABLED"
    assert spy.calls == 0


def test_rechaza_host_no_local(monkeypatch):
    spy = _PopenSpy()
    monkeypatch.setenv(_FLAG, "true")
    monkeypatch.setattr(awl.subprocess, "Popen", spy)
    res = ensure_agenda_web(base_url="http://10.0.0.5/AgendaWeb/")
    assert res["code"] == "NOT_LOCALHOST"
    assert spy.calls == 0


def test_ya_corriendo_no_arranca_ni_apaga(monkeypatch):
    spy = _PopenSpy()
    monkeypatch.setenv(_FLAG, "true")
    monkeypatch.setattr(awl.subprocess, "Popen", spy)
    monkeypatch.setattr(awl, "_responds", lambda *a, **kw: True)
    res = ensure_agenda_web(base_url=_LOCAL)
    assert res["ok"] is True
    assert res["already_running"] is True
    assert res["started_by_us"] is False
    assert spy.calls == 0
    assert stop_agenda_web(res)["stopped"] is False


def test_exe_faltante(monkeypatch):
    monkeypatch.setenv(_FLAG, "true")
    monkeypatch.setattr(awl, "_responds", lambda *a, **kw: False)
    monkeypatch.setattr(awl, "_resolve_iisexpress", lambda: None)
    res = ensure_agenda_web(base_url=_LOCAL)
    assert res["code"] == "IISEXPRESS_NOT_FOUND"
    assert res["remediation"]


def test_config_faltante(monkeypatch):
    monkeypatch.setenv(_FLAG, "true")
    monkeypatch.setattr(awl, "_responds", lambda *a, **kw: False)
    monkeypatch.setattr(awl, "_resolve_iisexpress", lambda: "C:/fake/iisexpress.exe")
    monkeypatch.setattr(awl, "_resolve_apphost_config", lambda: None)
    res = ensure_agenda_web(base_url=_LOCAL)
    assert res["code"] == "APPHOST_CONFIG_NOT_FOUND"


def test_timeout_mata_lo_que_arranco(monkeypatch):
    spy = _PopenSpy()
    monkeypatch.setenv(_FLAG, "true")
    monkeypatch.setattr(awl, "_responds", lambda *a, **kw: False)
    monkeypatch.setattr(awl, "_resolve_iisexpress", lambda: "C:/fake/iisexpress.exe")
    monkeypatch.setattr(awl, "_resolve_apphost_config", lambda: "C:/fake/apphost.config")
    monkeypatch.setattr(awl.subprocess, "Popen", spy)
    monkeypatch.setattr(awl.time, "sleep", lambda *_a: None)
    res = ensure_agenda_web(base_url=_LOCAL, timeout_s=1)
    assert res["code"] == "START_TIMEOUT"
    assert spy.terminated >= 1


def test_stop_solo_lo_propio():
    class _P:
        def __init__(self):
            self.killed = 0

        def terminate(self):
            self.killed += 1

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.killed += 1

    p = _P()
    assert stop_agenda_web({"started_by_us": True, "pid": 1, "_proc": p})["stopped"] is True
    assert p.killed == 1
    assert stop_agenda_web({"started_by_us": False, "pid": 1})["stopped"] is False


def test_deploy_mode_rechaza(monkeypatch):
    spy = _PopenSpy()
    monkeypatch.setenv(_FLAG, "true")
    monkeypatch.setenv("STACKY_DEPLOY_MODE", "1")
    monkeypatch.setattr(awl.subprocess, "Popen", spy)
    res = ensure_agenda_web(base_url=_LOCAL)
    assert res["code"] == "DEPLOY_MODE"
    assert spy.calls == 0


def test_sin_shell_en_el_modulo():
    """Sin shell=True: evita reinterpretacion de rutas con espacios."""
    from pathlib import Path
    src = (Path(awl.__file__)).read_text(encoding="utf-8")
    assert "shell=True" not in src
    assert src.count("started_by_us") >= 4


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
