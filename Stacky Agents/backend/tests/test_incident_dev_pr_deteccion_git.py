"""Auto-deteccion de repositorio git POR PROYECTO, para todos los proyectos.

Pedido del operador (2026-08-02, seguimiento):
  "Debes de hacerlo para todos los proyectos que tengan git y auto detectar si
   tiene o no git"

La deteccion se hace EJECUTANDO git contra el `workspace_root` de cada proyecto.
NO se infiere por el nombre de la carpeta ni por si la ruta contiene "SVN"/"GIT":
esa heuristica seria el mismo bug de antes con otro disfraz (una carpeta llamada
`C:/SVN/loquesea` puede ser un repo git perfectamente valido, y una llamada
`C:/GIT/x` puede no serlo).

Los casos (a) raiz, (b) subdirectorio y (d) worktree se prueban con git DE VERDAD
sobre `tmp_path`: son justamente los que un mock no probaria.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), text=True, capture_output=True, timeout=60,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


@pytest.fixture(autouse=True)
def _sin_memo():
    """Cada test parte del disco real, no del memo de otro test."""
    from services import incident_dev_pr as mod
    mod.invalidate_repo_detection()
    yield
    mod.invalidate_repo_detection()


@pytest.fixture
def repo(tmp_path):
    """Repo git real y minimo (sin red, sin remoto)."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t.local")
    _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("hola", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "inicial")
    return r


# ── (a) workspace_root ES la raiz del repo ───────────────────────────────────

def test_a_raiz_del_repo_se_detecta(repo):
    from services.incident_dev_pr import detect_repo
    d = detect_repo(str(repo))
    assert d["ok"] is True
    assert d["reason"] is None
    assert Path(d["repo_root"]).resolve() == repo.resolve()
    assert d["es_subdirectorio"] is False


# ── (b) workspace_root es un SUBDIRECTORIO del repo ──────────────────────────

def test_b_subdirectorio_cuenta_como_git_y_devuelve_el_TOPLEVEL(repo):
    """DECISION: un subdirectorio SI cuenta como "tiene git".

    Razon: el auto-PR no commitea desde el `workspace_root`, commitea rutas
    RELATIVAS AL TOPLEVEL que da `git rev-parse --show-toplevel` — que es lo que
    ya hacen `snapshot_worktree` y el post-hook. Rechazar el subdirectorio
    dejaria afuera el caso normal de un monorepo cuyo proyecto Stacky apunta a
    `<repo>/backend`. Se marca `es_subdirectorio` para poder AVISARLO: el diff
    que se commitea abarca TODO el repo, no solo esa subcarpeta."""
    sub = repo / "modulo" / "hondo"
    sub.mkdir(parents=True)
    from services.incident_dev_pr import detect_repo
    d = detect_repo(str(sub))
    assert d["ok"] is True
    assert Path(d["repo_root"]).resolve() == repo.resolve()   # el TOPLEVEL, no el subdir
    assert d["es_subdirectorio"] is True


# ── (c) NO es repo ───────────────────────────────────────────────────────────

def test_c1_carpeta_suelta_no_es_repo(tmp_path):
    from services.incident_dev_pr import detect_repo
    suelta = tmp_path / "suelta"
    suelta.mkdir()
    d = detect_repo(str(suelta))
    assert d["ok"] is False
    assert d["reason"] == "no_es_repo_git"


def test_c2_working_copy_de_svn_da_no_es_repo_git_con_PISTA(tmp_path):
    """La pista sale de que existe `.svn` EN DISCO, no del nombre de la carpeta."""
    from services.incident_dev_pr import detect_repo
    wc = tmp_path / "cualquier-nombre"
    (wc / ".svn").mkdir(parents=True)
    d = detect_repo(str(wc))
    assert d["ok"] is False
    assert d["reason"] == "no_es_repo_git"
    assert "subversion" in (d["pista"] or "").lower()


def test_c3_una_carpeta_llamada_SVN_que_SI_es_git_se_detecta_como_git(repo, tmp_path):
    """Anti-heuristica: el NOMBRE no decide. Un repo git dentro de una ruta que
    dice "SVN" tiene git, y hay que reconocerlo."""
    from services.incident_dev_pr import detect_repo
    disfraz = tmp_path / "C_desarrollo_SVN_RS" / "PROYECTO"
    disfraz.parent.mkdir(parents=True)
    _git(tmp_path, "clone", "-q", str(repo), str(disfraz))
    d = detect_repo(str(disfraz))
    assert d["ok"] is True, d
    assert d["reason"] is None


def test_c4_ruta_inexistente(tmp_path):
    from services.incident_dev_pr import detect_repo
    d = detect_repo(str(tmp_path / "no" / "existe"))
    assert d["ok"] is False
    assert d["reason"] == "ruta_inexistente"


def test_c5_ruta_que_es_un_archivo_no_una_carpeta(tmp_path):
    from services.incident_dev_pr import detect_repo
    f = tmp_path / "esto-es-un-archivo.txt"
    f.write_text("x", encoding="utf-8")
    d = detect_repo(str(f))
    assert d["ok"] is False
    assert d["reason"] == "ruta_no_es_carpeta"


def test_c6_unidad_caida_o_sin_permiso_no_se_confunde_con_no_es_repo(tmp_path, monkeypatch):
    """Una unidad de red caida NO es "no tiene git": es "no se pudo mirar". Si se
    reportara igual que una carpeta suelta, el operador saldria a convertir a git
    un repo que ya lo es."""
    from services import incident_dev_pr as mod
    real = os.stat

    def _stat_que_explota(path, *a, **k):
        if "caida" in str(path):
            raise OSError(64, "El nombre de red ya no esta disponible")
        return real(path, *a, **k)

    monkeypatch.setattr(mod.os, "stat", _stat_que_explota)
    d = mod.detect_repo(str(tmp_path / "unidad-caida"))
    assert d["ok"] is False
    assert d["reason"] == "ruta_inaccesible"


def test_c7_git_no_instalado_no_se_confunde_con_no_es_repo(repo, monkeypatch):
    """Sin git en el PATH, TODOS los proyectos dirian "no tiene git". Eso manda al
    operador a arreglar 8 repos sanos en vez de instalar git una vez."""
    from services import incident_dev_pr as mod

    def _sin_git(*a, **k):
        raise FileNotFoundError(2, "No such file or directory: 'git'")

    monkeypatch.setattr(mod.subprocess, "run", _sin_git)
    d = mod.detect_repo(str(repo))
    assert d["ok"] is False
    assert d["reason"] == "git_no_disponible"


def test_c8_git_colgado_da_su_propio_motivo(repo, monkeypatch):
    from services import incident_dev_pr as mod

    def _cuelga(*a, **k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(mod.subprocess, "run", _cuelga)
    d = mod.detect_repo(str(repo))
    assert d["ok"] is False
    assert d["reason"] == "git_sin_respuesta"


# ── (d) worktree / `.git` como ARCHIVO ───────────────────────────────────────

def test_d_git_worktree_con_dot_git_ARCHIVO_se_detecta(repo, tmp_path):
    """En un worktree `.git` es un ARCHIVO con `gitdir: ...`, no un directorio.
    Cualquier deteccion que haga `(ws/'.git').is_dir()` lo daria por NO-git."""
    wt = tmp_path / "wt"
    r = _git(repo, "worktree", "add", "-q", str(wt))
    if r.returncode != 0:  # pragma: no cover
        pytest.skip(f"git worktree no disponible: {r.stderr}")
    assert (wt / ".git").is_file(), "premisa del test: en un worktree .git es archivo"
    from services.incident_dev_pr import detect_repo
    d = detect_repo(str(wt))
    assert d["ok"] is True, d
    assert Path(d["repo_root"]).resolve() == wt.resolve()


def test_d2_el_dot_git_como_directorio_no_es_lo_que_se_mira(repo):
    """Contraste del anterior: la deteccion NO se apoya en el tipo de `.git`."""
    assert (repo / ".git").is_dir()
    from services.incident_dev_pr import detect_repo
    assert detect_repo(str(repo))["ok"] is True


# ── (e) sin workspace configurado ────────────────────────────────────────────

@pytest.mark.parametrize("vacio", [None, "", "   "])
def test_e_sin_workspace_configurado(vacio):
    from services.incident_dev_pr import detect_repo
    d = detect_repo(vacio)
    assert d["ok"] is False
    assert d["reason"] == "sin_workspace"


# ── Memo: no puede ser un martillo, ni quedarse pegado ───────────────────────

def test_memo_evita_correr_git_dos_veces_para_la_misma_ruta(repo, monkeypatch):
    from services import incident_dev_pr as mod
    llamadas = {"n": 0}
    real = mod.subprocess.run

    def _contar(*a, **k):
        llamadas["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(mod.subprocess, "run", _contar)
    mod.detect_repo(str(repo))
    n1 = llamadas["n"]
    assert n1 >= 1
    mod.detect_repo(str(repo))
    assert llamadas["n"] == n1, "la segunda consulta tiene que salir del memo"


def test_el_memo_cubre_TAMBIEN_el_remoto_no_solo_la_deteccion(repo, monkeypatch):
    """`preflight_repo` corre DOS comandos git por proyecto (rev-parse + remote
    get-url). Memoizar solo el primero deja la mitad del martillo en pie."""
    from services import incident_dev_pr as mod
    llamadas = {"n": 0}
    real = mod.subprocess.run

    def _contar(*a, **k):
        llamadas["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(mod.subprocess, "run", _contar)
    mod.detect_repo(str(repo))
    mod.remote_origin_url(str(repo))
    n1 = llamadas["n"]
    assert n1 >= 2, "premisa: la primera pasada ejecuta git de verdad"
    mod.detect_repo(str(repo))
    mod.remote_origin_url(str(repo))
    assert llamadas["n"] == n1, "la segunda pasada no puede volver a ejecutar git"


def test_invalidar_tira_TAMBIEN_el_remoto_memoizado(repo, monkeypatch):
    from services import incident_dev_pr as mod
    llamadas = {"n": 0}
    real = mod.subprocess.run

    def _contar(*a, **k):
        llamadas["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(mod.subprocess, "run", _contar)
    mod.remote_origin_url(str(repo))
    n1 = llamadas["n"]
    mod.invalidate_repo_detection()
    mod.remote_origin_url(str(repo))
    assert llamadas["n"] > n1


def test_memo_se_invalida_explicitamente(repo, monkeypatch):
    from services import incident_dev_pr as mod
    llamadas = {"n": 0}
    real = mod.subprocess.run

    def _contar(*a, **k):
        llamadas["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(mod.subprocess, "run", _contar)
    mod.detect_repo(str(repo))
    n1 = llamadas["n"]
    mod.invalidate_repo_detection()
    mod.detect_repo(str(repo))
    assert llamadas["n"] > n1


def test_memo_NO_se_queda_pegado_si_cambia_el_workspace_root(repo, tmp_path):
    """El memo se keyea por RUTA. Si el operador cambia el `workspace_root` del
    proyecto desde la UI, la clave cambia sola y el resultado es del disco nuevo
    — sin depender de invalidar a mano ni de un mtime de config."""
    from services.incident_dev_pr import detect_repo
    suelta = tmp_path / "otra"
    suelta.mkdir()
    assert detect_repo(str(repo))["ok"] is True
    assert detect_repo(str(suelta))["ok"] is False


def test_memo_caduca_por_tiempo(repo, monkeypatch):
    """Un `git init` posterior tiene que verse sin reiniciar Stacky."""
    from services import incident_dev_pr as mod
    reloj = {"t": 1000.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: reloj["t"])
    llamadas = {"n": 0}
    real = mod.subprocess.run

    def _contar(*a, **k):
        llamadas["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(mod.subprocess, "run", _contar)
    mod.detect_repo(str(repo))
    n1 = llamadas["n"]
    reloj["t"] += mod._DETECT_TTL_S + 1
    mod.detect_repo(str(repo))
    assert llamadas["n"] > n1


# ── Todos los proyectos, no solo el activo ───────────────────────────────────

def _proyectos(monkeypatch, mapa):
    """mapa: {nombre: workspace_root}. Sin tocar projects/ del operador."""
    from services import incident_dev_pr as mod

    class _Ctx:
        def __init__(self, name, ws):
            self.stacky_project_name = name
            self.workspace_root = ws
            self.tracker_type = "gitlab"

    from services import merge_request_provider as mrp_mod
    from services import project_context

    monkeypatch.setattr(mod, "_listar_proyectos", lambda: sorted(mapa))
    monkeypatch.setattr(
        project_context, "resolve_project_context",
        lambda p=None, *a, **k: _Ctx(p, mapa.get(p)) if p in mapa else None,
        raising=False,
    )
    prov = type("P", (), {"name": "gitlab"})()
    monkeypatch.setattr(mrp_mod, "get_merge_request_provider", lambda project=None: prov)
    return mod


def test_preflight_all_recorre_TODOS_los_proyectos(repo, tmp_path, monkeypatch, flags_on_dev_pr):
    suelta = tmp_path / "sin-git"
    suelta.mkdir()
    mod = _proyectos(monkeypatch, {"CON_GIT": str(repo), "SIN_GIT": str(suelta),
                                   "SIN_WS": None})
    filas = mod.preflight_all_projects()
    por_nombre = {f["project"]: f for f in filas}
    assert set(por_nombre) == {"CON_GIT", "SIN_GIT", "SIN_WS"}
    assert por_nombre["CON_GIT"]["ok"] is True
    assert por_nombre["SIN_GIT"]["reason"] == "no_es_repo_git"
    assert por_nombre["SIN_WS"]["reason"] == "sin_workspace"
    # cada motivo trae su mensaje propio, no uno generico compartido
    assert por_nombre["SIN_GIT"]["message"] != por_nombre["SIN_WS"]["message"]


def test_preflight_all_no_se_cae_si_UN_proyecto_explota(repo, monkeypatch, flags_on_dev_pr):
    """Un proyecto mal configurado no puede tapar el estado de los otros siete."""
    from services import incident_dev_pr as mod
    monkeypatch.setattr(mod, "_listar_proyectos", lambda: ["BUENO", "ROTO"])

    def _resolver(p=None, *a, **k):
        if p == "ROTO":
            raise RuntimeError("config podrida")
        c = type("C", (), {})()
        c.stacky_project_name = p
        c.workspace_root = str(repo)
        c.tracker_type = "gitlab"
        return c

    from services import merge_request_provider as mrp_mod
    from services import project_context
    monkeypatch.setattr(project_context, "resolve_project_context", _resolver, raising=False)
    prov = type("P", (), {"name": "gitlab"})()
    monkeypatch.setattr(mrp_mod, "get_merge_request_provider", lambda project=None: prov)

    filas = mod.preflight_all_projects()
    por_nombre = {f["project"]: f for f in filas}
    assert por_nombre["BUENO"]["ok"] is True
    assert por_nombre["ROTO"]["ok"] is False
    assert por_nombre["ROTO"]["reason"] == "sin_proyecto"


def test_preflight_repo_sigue_aceptando_el_proyecto_activo_por_defecto(repo, monkeypatch,
                                                                       flags_on_dev_pr):
    """Compatibilidad: los call sites que ya llaman `preflight_repo()` sin
    argumentos siguen andando."""
    mod = _proyectos(monkeypatch, {None: str(repo)})
    r = mod.preflight_repo()
    assert r["ok"] is True


@pytest.fixture
def flags_on_dev_pr():
    import config as cfg
    o = getattr(cfg.config, "STACKY_INCIDENT_DEV_PR_ENABLED", False)
    cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = True
    yield
    cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = o


# ── Cada reason tiene mensaje propio y estable ───────────────────────────────

def test_la_vista_de_conjunto_muestra_el_estado_git_AUNQUE_el_auto_pr_este_apagado(
    repo, tmp_path, monkeypatch,
):
    """Son dos preguntas distintas: "¿tiene git?" y "¿el auto-PR esta encendido?".
    Si la flag apagada tapara el estado de git, la vista no serviria para lo que
    el operador la pide (ver de un vistazo que proyectos estan listos)."""
    import config as cfg
    o = getattr(cfg.config, "STACKY_INCIDENT_DEV_PR_ENABLED", False)
    cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = False
    try:
        suelta = tmp_path / "sin-git"
        suelta.mkdir()
        mod = _proyectos(monkeypatch, {"A": str(repo), "B": str(suelta)})
        filas = {f["project"]: f for f in mod.preflight_all_projects()}
        assert filas["A"]["ok"] is True
        assert filas["B"]["reason"] == "no_es_repo_git"
        # y el preflight de UN proyecto si respeta la flag (el tilde no se ofrece)
        assert mod.preflight_repo("A")["reason"] == "feature_disabled"
    finally:
        cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = o


# ── Endpoint de la vista de conjunto ─────────────────────────────────────────

def test_endpoint_preflight_all_devuelve_una_fila_por_proyecto(monkeypatch):
    from services import incident_dev_pr as mod
    monkeypatch.setattr(mod, "preflight_all_projects", lambda: [
        {"ok": True, "project": "A", "reason": None, "message": "",
         "repo_root": "/r", "provider_label": "gitlab", "warning": None,
         "warning_message": "", "origin": "o", "workspace_root": "/ws",
         "tracker_type": "gitlab"},
        {"ok": False, "project": "B", "reason": "no_es_repo_git", "message": "no",
         "repo_root": None, "provider_label": None, "warning": None,
         "warning_message": "", "origin": None, "workspace_root": "/x",
         "tracker_type": None},
    ])
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    data = app.test_client().get("/api/incidents/dev-pr/preflight-all").get_json()
    assert data["ok"] is True
    assert [p["project"] for p in data["projects"]] == ["A", "B"]
    assert data["con_git"] == 1
    assert data["total"] == 2
    # el estado del auto-PR viaja aparte del estado de git
    assert "dev_pr_enabled" in data


def test_endpoint_preflight_all_con_refresh_INVALIDA_el_memo(monkeypatch):
    """El boton "Revisar de nuevo" tiene que revisar de nuevo DE VERDAD.

    Sin esto, el boton solo invalidaria el cache del navegador y el backend
    seguiria contestando desde su memo: el operador hace `git init`, aprieta el
    boton, y sigue viendo "no tiene git" hasta que venza el TTL. Un boton que
    miente es peor que no tener boton."""
    from services import incident_dev_pr as mod
    invalidaciones = []
    monkeypatch.setattr(mod, "invalidate_repo_detection",
                        lambda *a, **k: invalidaciones.append(True))
    monkeypatch.setattr(mod, "preflight_all_projects", lambda: [])
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()

    c.get("/api/incidents/dev-pr/preflight-all")
    assert invalidaciones == [], "sin refresh NO se tira el memo (seria un martillo)"

    c.get("/api/incidents/dev-pr/preflight-all?refresh=1")
    assert len(invalidaciones) == 1


def test_endpoint_preflight_con_refresh_invalida_solo_ese_proyecto(monkeypatch):
    from services import incident_dev_pr as mod
    vistas = []
    monkeypatch.setattr(mod, "invalidate_repo_detection", lambda ws=None: vistas.append(ws))
    monkeypatch.setattr(mod, "preflight_repo", lambda project=None: {
        "ok": True, "reason": None, "message": "", "warning": None,
        "warning_message": "", "repo_root": "/r", "origin": None,
        "workspace_root": "/ws", "tracker_type": "gitlab",
        "provider_label": "gitlab", "project": project,
    })
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.test_client().get("/api/incidents/dev-pr/preflight?project=X&refresh=1")
    assert len(vistas) == 1


def test_endpoint_preflight_all_nunca_rompe_la_pantalla(monkeypatch):
    from services import incident_dev_pr as mod

    def _boom():
        raise RuntimeError("catastrofe")

    monkeypatch.setattr(mod, "preflight_all_projects", _boom)
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/incidents/dev-pr/preflight-all")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert data["projects"] == []
    assert data["message"]


def test_cada_motivo_tiene_su_propio_mensaje_en_espaniol():
    from services.incident_dev_pr import _PREFLIGHT_MESSAGES, DETECT_REASONS
    vistos = {}
    for r in DETECT_REASONS:
        msg = _PREFLIGHT_MESSAGES.get(r)
        assert msg, f"el motivo '{r}' no tiene mensaje"
        assert msg not in vistos, f"'{r}' repite el mensaje de '{vistos.get(msg)}'"
        vistos[msg] = r
