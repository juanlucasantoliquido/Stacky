"""Plan 293 F1 — El catalogo CERRADO de verbos git.

Este archivo es el guardian del riesgo #1 del plan: el tablero corre git sobre el
repositorio REAL del operador, que tiene trabajo ajeno sin commitear y una sesion
paralela viva. La barrera es una ALLOWLIST que lanza, nunca una denylist.

Precedente medido dentro de este mismo repo: services/doc_documenter.py:651 usa
denylist {"push","merge","stash"} y se OLVIDO de "branch", asi que `git branch -D`
llega al repo del operador. services/night_foundry_workers.py:44-51 usa allowlist
y lanza ValueError. Este modulo copia la segunda.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from services import git_workbench as gw

_MODULO = Path(gw.__file__)


# ── Regla 1: verbo vacio ────────────────────────────────────────────────────
def test_01_lista_vacia_lanza():
    with pytest.raises(ValueError) as exc:
        gw._validar([])
    assert "<vacio>" in str(exc.value)


# ── Regla 2: verbo fuera de la allowlist ────────────────────────────────────
def test_02_verbo_desconocido_lanza():
    with pytest.raises(ValueError):
        gw._validar(["frobnicate"])


# ── Regla 3: verbo de escritura por el camino de lectura ────────────────────
def test_03_escritura_por_camino_de_lectura_lanza():
    # `commit` es un verbo conocido, pero el camino de lectura no puede usarlo.
    with pytest.raises(ValueError) as exc:
        gw._validar(["commit", "-F", "m.txt", "--", "a.py"], escritura=False)
    assert "lectura" in str(exc.value).lower()


def test_03b_escritura_declarada_si_permite_el_mismo_comando():
    gw._validar(["commit", "-F", "m.txt", "--", "a.py"], escritura=True)


# ── Regla 4: formas prohibidas, en CUALQUIER posicion ───────────────────────
@pytest.mark.parametrize(
    "args",
    [
        ["push", "origin", "rama", "--force"],
        ["push", "-f", "origin", "rama"],
        ["commit", "--amend", "-F", "m.txt", "--", "a.py"],
        ["add", "-A"],
        ["add", "--all"],
        ["switch", "--discard-changes", "rama"],
    ],
)
def test_04_formas_prohibidas_lanzan(args):
    with pytest.raises(ValueError):
        gw._validar(args, escritura=True)


# ── Regla 5 y 6: pathspec obligatoria ───────────────────────────────────────
def test_05_add_sin_doble_guion_lanza():
    with pytest.raises(ValueError):
        gw._validar(["add", "a.py"], escritura=True)


def test_05b_add_sin_rutas_lanza():
    with pytest.raises(ValueError):
        gw._validar(["add", "--"], escritura=True)


def test_05c_add_con_punto_lanza():
    with pytest.raises(ValueError):
        gw._validar(["add", "--", "."], escritura=True)


def test_06_commit_sin_pathspec_lanza():
    # LA barrera del riesgo #1: sin `--` el commit toma lo que haya en el indice,
    # que puede ser trabajo de la sesion paralela.
    with pytest.raises(ValueError) as exc:
        gw._validar(["commit", "-F", "m.txt"], escritura=True)
    assert "pathspec" in str(exc.value).lower()


def test_06b_commit_con_doble_guion_pero_sin_rutas_lanza():
    with pytest.raises(ValueError):
        gw._validar(["commit", "-F", "m.txt", "--"], escritura=True)


# ── Regla 7: `config` solo en modo lectura de UNA clave ─────────────────────
def test_07_config_get_permitido():
    gw._validar(["config", "--get", "user.email"])


def test_07b_config_que_escribe_lanza():
    # `git config user.email x` ESCRIBE en el .git/config del operador.
    with pytest.raises(ValueError):
        gw._validar(["config", "user.email", "x@y.z"])


def test_07c_config_global_lanza():
    with pytest.raises(ValueError):
        gw._validar(["config", "--global", "--get", "user.email"])


# ── Regla 8: push con forma exacta ──────────────────────────────────────────
def test_08_push_forma_exacta_permitido():
    gw._validar(["push", "origin", "mi-rama"], escritura=True)


def test_08b_push_con_argumentos_de_mas_lanza():
    with pytest.raises(ValueError):
        gw._validar(["push", "origin", "mi-rama", "--mirror"], escritura=True)


# ── Regla 9: merge solo --ff-only ───────────────────────────────────────────
def test_09_merge_ff_only_permitido():
    gw._validar(["merge", "--ff-only", "@{u}"], escritura=True)


def test_09b_merge_sin_ff_only_lanza():
    with pytest.raises(ValueError):
        gw._validar(["merge", "origin/main"], escritura=True)


# ── Verbos destructivos, uno por uno ────────────────────────────────────────
@pytest.mark.parametrize(
    "verbo",
    ["reset", "clean", "stash", "rebase", "checkout", "branch", "filter-branch", "cherry-pick"],
)
def test_10_verbos_destructivos_no_existen(verbo):
    with pytest.raises(ValueError):
        gw._validar([verbo], escritura=True)


# ── Camino feliz de lectura ─────────────────────────────────────────────────
def test_11_lectura_feliz_no_lanza():
    gw._validar(["status", "--porcelain=v2", "--branch"])
    gw._validar(["rev-parse", "--show-toplevel"])
    gw._validar(["log", "-n5", "--format=%H"])
    gw._validar(["for-each-ref", "--format=%(refname:short)", "refs/heads"])


# ── Censo por REFERENCIA: un solo punto de ejecucion ────────────────────────
def test_12_un_solo_subprocess_run_en_el_modulo():
    """El AST da CERO si la llamada va por alias, asi que se censa por texto.

    Debe haber EXACTAMENTE un `subprocess.run(` en todo el modulo, y tiene que
    estar dentro de `_run_git`: si aparece un segundo, hay un camino que no pasa
    por el guard.
    """
    texto = _MODULO.read_text(encoding="utf-8")
    assert texto.count("subprocess.run(") == 1

    cuerpo = texto.split("def _run_git(", 1)[1]
    assert "subprocess.run(" in cuerpo


def test_13_run_git_llama_al_validador():
    """Regresion del guard: `_run_git` no puede ejecutar sin validar antes."""
    cuerpo = _MODULO.read_text(encoding="utf-8").split("def _run_git(", 1)[1]
    pos_validar = cuerpo.find("_validar(")
    pos_run = cuerpo.find("subprocess.run(")
    assert pos_validar != -1, "_run_git no llama a _validar"
    assert pos_validar < pos_run, "_validar tiene que correr ANTES de subprocess.run"


def test_14_no_hay_shell_true():
    texto = _MODULO.read_text(encoding="utf-8")
    assert not re.search(r"shell\s*=\s*True", texto)
