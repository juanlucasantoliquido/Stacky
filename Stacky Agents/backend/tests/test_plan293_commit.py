"""Plan 293 F6 — Elegir archivos y confirmar cambios. EL RIESGO #1 DEL PLAN.

El tablero corre git sobre el repositorio REAL del operador. Ese arbol tiene
normalmente trabajo sin confirmar de otras series y una sesion paralela viva que
`git worktree list` NO detecta. Un boton que haga `add -A` le roba el trabajo al
otro y lo publica.

Los tests corren contra repositorios git DE VERDAD en un temporal: el
comportamiento de git ES lo que se prueba. NUNCA se toca el repo de Stacky.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from services import git_local_writer as glw


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    ).stdout or ""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-b", "principal")
    _git(r, "config", "user.email", "prueba@local")
    _git(r, "config", "user.name", "Prueba")
    for n in range(1, 6):
        (r / f"f{n}.txt").write_text("original\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "inicial")
    for n in range(1, 6):
        (r / f"f{n}.txt").write_text(f"cambiado {n}\n", encoding="utf-8")
    return r


@pytest.fixture(autouse=True)
def _escritura_encendida(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_WORKBENCH_WRITE_ENABLED", True, raising=False)


# ══════════════════════════════════════════════════════════════════════════════
# EL CASO QUE JUSTIFICA LA FASE
# ══════════════════════════════════════════════════════════════════════════════
def test_01_el_commit_lleva_SOLO_lo_seleccionado_con_trabajo_ajeno_stageado(repo):
    """Cinco archivos sucios, se eligen DOS, y la sesion paralela deja los cinco
    preparados por fuera. El commit tiene que llevar exactamente dos."""
    _git(repo, "add", "-A")  # <- la sesion paralela, simulada

    res = glw.confirmar_cambios(raiz=repo, rutas=["f1.txt", "f2.txt"], mensaje="solo dos")

    assert res["ok"] is True, res
    entraron = {l.split("|")[0].strip() for l in _git(repo, "show", "--stat", "--name-only", "--format=", "HEAD").splitlines() if l.strip()}
    assert entraron == {"f1.txt", "f2.txt"}, f"entraron de mas o de menos: {entraron}"

    # Los otros TRES siguen modificados y sin confirmar: no se los llevo nadie.
    pendientes = _git(repo, "status", "--porcelain=v1")
    for n in (3, 4, 5):
        assert f"f{n}.txt" in pendientes, f"f{n}.txt desaparecio del pendiente: {pendientes}"


def test_02_ningun_comando_usa_add_menos_A(repo, monkeypatch):
    """Censo por REFERENCIA de lo que se ejecuto de verdad."""
    vistos: list[list[str]] = []
    original = glw.gw._run_git

    def espia(args, cwd, **kw):
        vistos.append(list(args))
        return original(args, cwd, **kw)

    monkeypatch.setattr(glw.gw, "_run_git", espia)
    glw.confirmar_cambios(raiz=repo, rutas=["f1.txt"], mensaje="x")

    planos = [tok for cmd in vistos for tok in cmd]
    assert "-A" not in planos, f"se ejecuto un add -A: {vistos}"
    assert "--all" not in planos
    assert "." not in planos
    # Y el commit SI llevo pathspec.
    commits = [c for c in vistos if c and c[0] == "commit"]
    assert commits, "no se ejecuto ningun commit"
    for c in commits:
        assert "--" in c, f"commit sin pathspec: {c}"


def test_03_archivo_sin_seguimiento_seleccionado_entra(repo):
    (repo / "nuevo.txt").write_text("soy nuevo\n", encoding="utf-8")
    res = glw.confirmar_cambios(raiz=repo, rutas=["nuevo.txt"], mensaje="agrega nuevo")
    assert res["ok"] is True, res
    entraron = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert "nuevo.txt" in entraron


def test_04_archivo_sin_seguimiento_NO_seleccionado_no_entra(repo):
    (repo / "ajeno_nuevo.txt").write_text("de otro\n", encoding="utf-8")
    glw.confirmar_cambios(raiz=repo, rutas=["f1.txt"], mensaje="solo f1")
    entraron = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert "ajeno_nuevo.txt" not in entraron
    assert "ajeno_nuevo.txt" in _git(repo, "status", "--porcelain=v1")


def test_05_ruta_absoluta_rechazada_sin_correr_git(repo, monkeypatch):
    vistos = []
    monkeypatch.setattr(glw.gw, "_run_git", lambda *a, **k: vistos.append(a) or None)
    res = glw.confirmar_cambios(raiz=repo, rutas=[str(repo / "f1.txt")], mensaje="x")
    assert res["ok"] is False
    assert res["codigo"] == "ruta_invalida"
    assert vistos == [], "se ejecuto git con una ruta invalida"


def test_06_ruta_con_dos_puntos_rechazada(repo):
    res = glw.confirmar_cambios(raiz=repo, rutas=["../fuera.txt"], mensaje="x")
    assert res["ok"] is False and res["codigo"] == "ruta_invalida"


def test_07_index_lock_bloquea_sin_correr_git(repo, monkeypatch):
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")
    vistos = []
    monkeypatch.setattr(glw.gw, "_run_git", lambda *a, **k: vistos.append(a) or None)
    res = glw.confirmar_cambios(raiz=repo, rutas=["f1.txt"], mensaje="x")
    assert res["ok"] is False and res["codigo"] == "otra_operacion_en_curso"
    assert vistos == []


def test_08_seleccion_vacia_no_commitea(repo):
    res = glw.confirmar_cambios(raiz=repo, rutas=[], mensaje="x")
    assert res["ok"] is False and res["codigo"] == "nada_seleccionado"
    assert "inicial" in _git(repo, "log", "--format=%s")


def test_09_mensaje_con_comillas_backticks_y_saltos(repo):
    """Por esto se usa -F y no -m: un mensaje asi rompe el armado por argumentos
    y en Windows es un camino de inyeccion."""
    mensaje = 'arregla "esto" y `aquello`\n\nsegunda linea con $VAR y %OTRA%'
    res = glw.confirmar_cambios(raiz=repo, rutas=["f1.txt"], mensaje=mensaje)
    assert res["ok"] is True, res
    guardado = _git(repo, "log", "-1", "--format=%B").strip()
    assert guardado == mensaje.strip()


def test_10_sin_identidad_explicita_SE_GUARDA_IGUAL(tmp_path, monkeypatch):
    """MEDIDO, contra lo que suponia la primera version de este test.

    `git commit` SIN user.email NO falla: git DERIVA la identidad de
    usuario@maquina y guarda igual (exit 0, con un aviso). Bloquear apoyandose
    en que `config --get user.email` sale con exit 1 seria un FALSO BLOQUEO
    permanente en cualquier maquina sin identidad explicita — el tablero
    quedaria inutilizable sin motivo real.

    Por eso `identidad_derivada` es AVISO (git_workbench.CODIGOS_AVISO) y no
    bloqueo, y el escritor no pregunta por la identidad antes de guardar.
    """
    r = tmp_path / "sinid"
    r.mkdir()
    _git(r, "init", "-b", "principal")
    (r / "a.txt").write_text("x\n", encoding="utf-8")
    vacia = tmp_path / "cfg-vacio"
    vacia.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(vacia))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(vacia))

    res = glw.confirmar_cambios(raiz=r, rutas=["a.txt"], mensaje="x")
    assert res["ok"] is True, res
    assert "a.txt" in _git(r, "show", "--name-only", "--format=", "HEAD").split()

    # El semaforo si lo AVISA, para que la pantalla lo diga sin impedir nada.
    from services import git_workbench as gw
    ov = gw.repo_overview(r)
    assert ov["identidad_ok"] is False
    sem = gw.evaluar_operacion(
        repo=ov, accion="confirmar",
        flags={"escritura": True, "envio": True}, seleccion=["a.txt"],
    )
    assert "identidad_derivada" in [a["codigo"] for a in sem["avisos"]]


def test_10b_carpeta_como_ruta_rechazada(repo):
    """PROBADO: una pathspec de CARPETA es RECURSIVA. `commit -- sub` se lleva
    todo lo modificado debajo, que es exactamente el robo de trabajo ajeno que
    esta fase existe para impedir."""
    sub = repo / "sub"
    sub.mkdir()
    (sub / "ajeno.txt").write_text("de otro\n", encoding="utf-8")
    res = glw.confirmar_cambios(raiz=repo, rutas=["sub"], mensaje="x")
    assert res["ok"] is False and res["codigo"] == "ruta_es_carpeta"


def test_11_el_archivo_temporal_del_mensaje_no_queda(repo):
    antes = set(Path(repo).glob("**/*.stacky-msg*"))
    glw.confirmar_cambios(raiz=repo, rutas=["f1.txt"], mensaje="x")
    assert set(Path(repo).glob("**/*.stacky-msg*")) == antes


def test_12_flag_apagada_no_corre_git(repo, monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_WORKBENCH_WRITE_ENABLED", False, raising=False)
    vistos = []
    monkeypatch.setattr(glw.gw, "_run_git", lambda *a, **k: vistos.append(a) or None)
    res = glw.confirmar_cambios(raiz=repo, rutas=["f1.txt"], mensaje="x")
    assert res["ok"] is False and res["codigo"] == "escritura_apagada"
    assert vistos == []


def test_13_conflictos_presentes_bloquean(repo):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    _git(repo, "switch", "-c", "otra")
    (repo / "f1.txt").write_text("otra\n", encoding="utf-8")
    _git(repo, "commit", "-am", "otra")
    _git(repo, "switch", "principal")
    (repo / "f1.txt").write_text("principal\n", encoding="utf-8")
    _git(repo, "commit", "-am", "principal")
    _git(repo, "merge", "otra")

    res = glw.confirmar_cambios(raiz=repo, rutas=["f1.txt"], mensaje="x")
    assert res["ok"] is False and res["codigo"] == "conflictos_presentes"


def test_14_devuelve_el_identificador_de_lo_guardado(repo):
    res = glw.confirmar_cambios(raiz=repo, rutas=["f1.txt"], mensaje="x")
    assert res["ok"] is True
    assert res["sha"] and len(res["sha"]) >= 7
    assert res["archivos"] == ["f1.txt"]
