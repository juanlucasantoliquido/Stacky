"""Plan 293 F9 — Ramas (listar, crear, cambiar) y F10 — Historial.

`switch` SIN -f se niega solo cuando el cambio pisaria trabajo no confirmado.
Esa negativa ES la barrera: se traduce a castellano en vez de forzarse.
Borrar ramas NO existe en este plan: `branch` no esta en el catalogo.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from services import git_local_writer as glw
from services import git_workbench as gw


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
    (r / "a.txt").write_text("uno\n", encoding="utf-8")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-m", "primero")
    return r


@pytest.fixture(autouse=True)
def _escritura_encendida(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_WORKBENCH_WRITE_ENABLED", True, raising=False)


# ── F9: listar ──────────────────────────────────────────────────────────────
def test_01_listar_marca_la_actual(repo):
    _git(repo, "switch", "-c", "otra")
    _git(repo, "switch", "principal")
    res = gw.listar_ramas(repo)
    assert res["ok"] is True
    nombres = {r["nombre"]: r for r in res["ramas"]}
    assert {"principal", "otra"} <= set(nombres)
    assert nombres["principal"]["actual"] is True
    assert nombres["otra"]["actual"] is False


def test_02_listar_en_carpeta_sin_repo_degrada(tmp_path):
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    res = gw.listar_ramas(vacia)
    assert res["ok"] is True and res["available"] is False
    assert res["ramas"] == []


# ── F9: crear ───────────────────────────────────────────────────────────────
def test_03_crear_rama(repo):
    res = glw.crear_rama(raiz=repo, nombre="mi-trabajo")
    assert res["ok"] is True, res
    assert "mi-trabajo" in _git(repo, "rev-parse", "--abbrev-ref", "HEAD")


@pytest.mark.parametrize(
    "nombre",
    [
        "-peligrosa",       # empieza con guion: git la lee como opcion
        "a..b",             # rango de revisiones
        "x.lock",           # git reserva el sufijo .lock
        "",                 # vacio
        "a" * 101,          # demasiado largo
        "con espacio",
        "con~tilde",
        "dos:puntos",
    ],
)
def test_04_nombre_invalido_no_llega_a_git(repo, nombre, monkeypatch):
    vistos = []
    monkeypatch.setattr(gw, "_run_git", lambda *a, **k: vistos.append(a) or None)
    res = glw.crear_rama(raiz=repo, nombre=nombre)
    assert res["ok"] is False and res["codigo"] == "nombre_invalido"
    assert vistos == [], f"se ejecuto git con el nombre {nombre!r}"


# ── F9: cambiar ─────────────────────────────────────────────────────────────
def test_05_cambiar_limpio(repo):
    _git(repo, "switch", "-c", "otra")
    _git(repo, "switch", "principal")
    res = glw.cambiar_rama(raiz=repo, nombre="otra")
    assert res["ok"] is True, res
    assert "otra" in _git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def test_06_cambiar_que_pisaria_trabajo_se_NIEGA_y_no_pierde_nada(repo):
    """LA barrera de esta fase: `switch` sin -f se niega solo. El trabajo sin
    confirmar queda intacto y el mensaje se traduce, no se fuerza."""
    _git(repo, "switch", "-c", "otra")
    (repo / "a.txt").write_text("version de otra\n", encoding="utf-8")
    _git(repo, "commit", "-am", "en otra")
    _git(repo, "switch", "principal")

    (repo / "a.txt").write_text("trabajo sin guardar\n", encoding="utf-8")

    res = glw.cambiar_rama(raiz=repo, nombre="otra")
    assert res["ok"] is False
    assert res["codigo"] == "cambio_bloqueado_por_trabajo_sin_guardar"
    # Lo importante: el trabajo NO se perdio.
    assert (repo / "a.txt").read_text(encoding="utf-8") == "trabajo sin guardar\n"
    assert "principal" in _git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def test_07_ningun_comando_lleva_borrado_ni_fuerza(repo, monkeypatch):
    vistos: list[list[str]] = []
    original = gw._run_git

    def espia(args, cwd, **kw):
        vistos.append(list(args))
        return original(args, cwd, **kw)

    monkeypatch.setattr(gw, "_run_git", espia)
    glw.crear_rama(raiz=repo, nombre="otra-mas")
    glw.cambiar_rama(raiz=repo, nombre="principal")

    planos = [t for c in vistos for t in c]
    for prohibido in ("-D", "--delete", "-f", "--force", "-C", "--discard-changes"):
        assert prohibido not in planos, f"aparecio {prohibido} en {vistos}"
    assert "branch" not in [c[0] for c in vistos], "el verbo branch no existe en este plan"


def test_08_flag_apagada_no_corre_git(repo, monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_WORKBENCH_WRITE_ENABLED", False, raising=False)
    vistos = []
    monkeypatch.setattr(gw, "_run_git", lambda *a, **k: vistos.append(a) or None)
    assert glw.crear_rama(raiz=repo, nombre="x")["codigo"] == "escritura_apagada"
    assert glw.cambiar_rama(raiz=repo, nombre="x")["codigo"] == "escritura_apagada"
    assert vistos == []


# ── F10: historial ──────────────────────────────────────────────────────────
def test_09_historial_en_orden(repo):
    (repo / "b.txt").write_text("dos\n", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-m", "segundo")
    res = gw.historial(repo, n=10)
    assert res["ok"] is True and res["available"] is True
    asuntos = [c["asunto"] for c in res["commits"]]
    assert asuntos == ["segundo", "primero"]
    primero = res["commits"][0]
    assert primero["sha_corto"] and primero["autor"] and primero["fecha"]


def test_10_asunto_con_separadores_y_tildes_intacto(repo):
    asunto = "arregla el | pipe, las \"comillas\" y los acentos: ñ á"
    (repo / "c.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "c.txt")
    _git(repo, "commit", "-m", asunto)
    res = gw.historial(repo, n=1)
    assert res["commits"][0]["asunto"] == asunto


def test_11_repo_sin_commits_no_es_error(tmp_path):
    r = tmp_path / "nuevo"
    r.mkdir()
    _git(r, "init", "-b", "principal")
    res = gw.historial(r, n=5)
    assert res["ok"] is True and res["available"] is True
    assert res["commits"] == []


@pytest.mark.parametrize("pedido,esperado", [(0, 1), (-5, 1), (9999, 100)])
def test_12_n_fuera_de_rango_se_acota(repo, pedido, esperado):
    res = gw.historial(repo, n=pedido)
    assert res["ok"] is True
    assert res["n"] == esperado


def test_13_historial_sin_repo_degrada(tmp_path):
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    res = gw.historial(vacia, n=5)
    assert res["ok"] is True and res["available"] is False
    assert res["commits"] == []
