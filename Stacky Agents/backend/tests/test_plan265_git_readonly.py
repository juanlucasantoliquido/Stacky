"""Plan 265 F4 — Panel de Repositorio de la consola (SOLO LECTURA). 13 casos.

GET /api/git/status?workspace=<ruta> y GET /api/git/diff?workspace=<ruta>&path=<archivo>
son rutas NUEVAS creadas por este plan. Todo el trabajo de subproceso vive en
services/console_repo.py, copiado del patrón de git_context.py:60 y
plans_board.py:644/665-681 (PROHIBIDO importar de plans_board.py).
"""
from __future__ import annotations

import subprocess

import pytest


@pytest.fixture
def registered_workspace(tmp_path, monkeypatch):
    """Workspace 'conocido' por project_manager: un dir real con `.git/` propio."""
    (tmp_path / ".git").mkdir()
    import project_manager
    monkeypatch.setattr(
        project_manager,
        "get_all_projects",
        lambda: [{"name": "demo", "workspace_root": str(tmp_path)}],
    )
    return tmp_path


@pytest.fixture
def app_repo_on(monkeypatch):
    import config as cfg
    original = getattr(cfg.config, "STACKY_CONSOLE_REPO_PANEL_ENABLED", True)
    cfg.config.STACKY_CONSOLE_REPO_PANEL_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_CONSOLE_REPO_PANEL_ENABLED = original


@pytest.fixture
def app_repo_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_CONSOLE_REPO_PANEL_ENABLED", True)
    cfg.config.STACKY_CONSOLE_REPO_PANEL_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_CONSOLE_REPO_PANEL_ENABLED = original


def _count_subprocess_calls(monkeypatch):
    calls = {"n": 0}
    real_run = subprocess.run

    def _counting_run(*args, **kwargs):
        calls["n"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _counting_run)
    return calls


# ---------------------------------------------------------------------------
# 1-3: entradas inválidas -> 400, git NUNCA se ejecuta
# ---------------------------------------------------------------------------

def test_1_workspace_no_registrado_400_sin_ejecutar_git(app_repo_on, tmp_path, monkeypatch):
    calls = _count_subprocess_calls(monkeypatch)
    import project_manager
    monkeypatch.setattr(project_manager, "get_all_projects", lambda: [])
    resp = app_repo_on.test_client().get(f"/api/git/status?workspace={tmp_path}")
    assert resp.status_code == 400
    assert calls["n"] == 0


def test_2_path_con_dotdot_400_sin_ejecutar_git(app_repo_on, registered_workspace, monkeypatch):
    calls = _count_subprocess_calls(monkeypatch)
    resp = app_repo_on.test_client().get(
        f"/api/git/diff?workspace={registered_workspace}&path=../fuera.txt"
    )
    assert resp.status_code == 400
    assert calls["n"] == 0


def test_3_path_absoluto_400_sin_ejecutar_git(app_repo_on, registered_workspace, monkeypatch):
    calls = _count_subprocess_calls(monkeypatch)
    absolute = str(registered_workspace / "x.txt")
    resp = app_repo_on.test_client().get(
        f"/api/git/diff?workspace={registered_workspace}&path={absolute}"
    )
    assert resp.status_code == 400
    assert calls["n"] == 0


# ---------------------------------------------------------------------------
# 4-6: degradaciones de repo_status — nunca 500
# ---------------------------------------------------------------------------

def test_4_workspace_sin_repositorio_200_available_false(app_repo_on, tmp_path, monkeypatch):
    import project_manager
    monkeypatch.setattr(
        project_manager, "get_all_projects",
        lambda: [{"name": "demo", "workspace_root": str(tmp_path)}],
    )
    # OJO: sin crear tmp_path/.git -> no hay repositorio.
    resp = app_repo_on.test_client().get(f"/api/git/status?workspace={tmp_path}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["available"] is False
    assert data["reason"]


def test_5_git_no_instalado_no_es_500(app_repo_on, registered_workspace, monkeypatch):
    def _boom(*args, **kwargs):
        raise FileNotFoundError("git no encontrado")

    monkeypatch.setattr(subprocess, "run", _boom)
    resp = app_repo_on.test_client().get(f"/api/git/status?workspace={registered_workspace}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["available"] is False


def test_6_timeout_expired_reason_menciona_tiempo(app_repo_on, registered_workspace, monkeypatch):
    def _boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["git", "status"], timeout=5)

    monkeypatch.setattr(subprocess, "run", _boom)
    resp = app_repo_on.test_client().get(f"/api/git/status?workspace={registered_workspace}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["available"] is False
    assert "tiempo" in data["reason"].lower()


# ---------------------------------------------------------------------------
# 7: status con salida mockeada de 3 archivos
# ---------------------------------------------------------------------------

def test_7_status_con_tres_archivos(app_repo_on, registered_workspace, monkeypatch):
    porcelain = " M archivo1.py\n?? archivo2.py\nA  archivo3.py\n"

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=porcelain, stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    resp = app_repo_on.test_client().get(f"/api/git/status?workspace={registered_workspace}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["files"]) == 3
    for f in data["files"]:
        assert f["path"]
        assert f["status"]


# ---------------------------------------------------------------------------
# 8: diff > 200 KB truncado
# ---------------------------------------------------------------------------

def test_8_diff_grande_se_trunca(app_repo_on, registered_workspace, monkeypatch):
    huge_diff = "+linea\n" * 60_000  # bien por encima de 200 KB

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=huge_diff, stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    (registered_workspace / "grande.txt").write_text("x", encoding="utf-8")
    resp = app_repo_on.test_client().get(
        f"/api/git/diff?workspace={registered_workspace}&path=grande.txt"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["truncated"] is True
    assert len(data["diff"]) <= 200 * 1024


# ---------------------------------------------------------------------------
# 9: el comando pasado al subproceso es una LISTA, shell falsy
# ---------------------------------------------------------------------------

def test_9_comando_es_lista_shell_falsy(app_repo_on, registered_workspace, monkeypatch):
    captured = {}

    def _fake_run(*args, **kwargs):
        captured["args"] = args[0] if args else kwargs.get("args")
        captured["shell"] = kwargs.get("shell")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    app_repo_on.test_client().get(f"/api/git/status?workspace={registered_workspace}")
    assert isinstance(captured["args"], list)
    assert not captured.get("shell")


# ---------------------------------------------------------------------------
# 10: flag OFF -> envelope de deshabilitado, git NO se ejecuta
# ---------------------------------------------------------------------------

def test_10_flag_off_no_ejecuta_git(app_repo_off, registered_workspace, monkeypatch):
    calls = _count_subprocess_calls(monkeypatch)
    resp = app_repo_off.test_client().get(f"/api/git/status?workspace={registered_workspace}")
    assert resp.status_code in (200, 404)
    assert calls["n"] == 0
    data = resp.get_json()
    assert data.get("available") is False or data.get("error") == "feature_disabled"


# ---------------------------------------------------------------------------
# 11: barrido de escritura — lee el TEXTO de api/git.py y console_repo.py
# ---------------------------------------------------------------------------

_FORBIDDEN_WRITE_SUBCOMMANDS = [
    '"commit"', "'commit'",
    '"push"', "'push'",
    '"add"', "'add'",
    '"checkout"', "'checkout'",
    '"reset"', "'reset'",
    '"rm"', "'rm'",
    '"merge"', "'merge'",
    '"rebase"', "'rebase'",
    '"stash"', "'stash'",
    '"clean"', "'clean'",
    '"apply"', "'apply'",
]


def test_11_barrido_de_escritura():
    import pathlib
    backend_dir = pathlib.Path(__file__).resolve().parents[1]
    targets = [backend_dir / "api" / "git.py", backend_dir / "services" / "console_repo.py"]
    hits = []
    for target in targets:
        text = target.read_text(encoding="utf-8")
        for bad in _FORBIDDEN_WRITE_SUBCOMMANDS:
            if bad in text:
                hits.append(f"{target.name}: {bad}")
    assert hits == [], f"subcomandos de escritura encontrados: {hits}"


# ---------------------------------------------------------------------------
# 12: archivo binario en el diff
# ---------------------------------------------------------------------------

def test_12_diff_binario_no_manda_bytes_crudos(app_repo_on, registered_workspace, monkeypatch):
    binary_marker = "Binary files a/foo.bin and b/foo.bin differ\n"

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=binary_marker, stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    (registered_workspace / "foo.bin").write_bytes(b"\x00\x01\x02")
    resp = app_repo_on.test_client().get(
        f"/api/git/diff?workspace={registered_workspace}&path=foo.bin"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["reason"] and "binari" in data["reason"].lower()


# ---------------------------------------------------------------------------
# 13: sesión concurrente (.git/index.lock) — nunca 500, nunca cuelgue
# ---------------------------------------------------------------------------

def test_13_index_lock_no_500(app_repo_on, registered_workspace):
    (registered_workspace / ".git" / "index.lock").write_text("", encoding="utf-8")
    resp = app_repo_on.test_client().get(f"/api/git/status?workspace={registered_workspace}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["available"] is False
    assert data["reason"]
