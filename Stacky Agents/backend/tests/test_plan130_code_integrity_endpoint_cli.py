"""tests/test_plan130_code_integrity_endpoint_cli.py — Plan 130 F2.

GET /api/diag/code-integrity + CLI scripts/check_code_integrity.py. Fixtures
app_flag_off/app_flag_on copiadas de test_plan87_devops_endpoints.py:6-29
cambiando el attr a STACKY_CODE_INTEGRITY_ENABLED. El CLI se testea IN-PROCESS
importando main (nada de subprocess). 7 casos.
"""
import sys
from pathlib import Path

import pytest


@pytest.fixture
def app_flag_off():
    """App con flag STACKY_CODE_INTEGRITY_ENABLED=False."""
    import config as cfg

    original = getattr(cfg.config, "STACKY_CODE_INTEGRITY_ENABLED", False)
    cfg.config.STACKY_CODE_INTEGRITY_ENABLED = False
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_CODE_INTEGRITY_ENABLED = original


@pytest.fixture
def app_flag_on():
    """App con flag STACKY_CODE_INTEGRITY_ENABLED=True."""
    import config as cfg

    original = getattr(cfg.config, "STACKY_CODE_INTEGRITY_ENABLED", False)
    cfg.config.STACKY_CODE_INTEGRITY_ENABLED = True
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_CODE_INTEGRITY_ENABLED = original


def test_endpoint_404_flag_off(app_flag_off):
    client = app_flag_off.test_client()
    resp = client.get("/api/diag/code-integrity")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "code_integrity_disabled"


def test_endpoint_200_shape(app_flag_on, monkeypatch):
    import services.code_integrity as ci

    fake_report = {
        "ok": True, "root": "X", "files_scanned": 1, "elapsed_ms": 1,
        "syntax_errors": [], "broken_imports": [],
    }
    monkeypatch.setattr(ci, "run_checks", lambda *a, **kw: fake_report)
    client = app_flag_on.test_client()
    resp = client.get("/api/diag/code-integrity")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {
        "ok", "root", "files_scanned", "elapsed_ms", "syntax_errors", "broken_imports",
    }


def test_endpoint_error_interno_sin_leak(app_flag_on, monkeypatch):
    import services.code_integrity as ci

    def _raise(*a, **kw):
        raise RuntimeError("C:\\secreto")

    monkeypatch.setattr(ci, "run_checks", _raise)
    client = app_flag_on.test_client()
    resp = client.get("/api/diag/code-integrity")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"ok": False, "error": "RuntimeError"}
    assert "secreto" not in resp.get_data(as_text=True)


def test_ruta_sin_doble_prefijo(app_flag_on):
    rules = [str(r) for r in app_flag_on.url_map.iter_rules()]
    assert any(r == "/api/diag/code-integrity" for r in rules)
    assert not any("/api/api/diag/code-integrity" in r for r in rules)


def _cli_main():
    backend_dir = Path(__file__).resolve().parents[1]
    scripts_dir = backend_dir / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import check_code_integrity

    return check_code_integrity.main


def test_cli_exit_0(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api" / "ok.py").write_text("x = 1\n", encoding="utf-8")

    main = _cli_main()
    exit_code = main(["--root", str(tmp_path)])
    assert exit_code == 0


def test_cli_exit_1_y_stdout(tmp_path, capsys):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api" / "roto.py").write_text(
        '"""placeholder"""\n# comentario\ndef f(:\n    pass\n', encoding="utf-8"
    )

    main = _cli_main()
    exit_code = main(["--root", str(tmp_path)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "roto.py:3" in out


def test_cli_exit_2(monkeypatch):
    main = _cli_main()
    import services.code_integrity as ci

    def _raise(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(ci, "run_checks", _raise)
    exit_code = main([])
    assert exit_code == 2
