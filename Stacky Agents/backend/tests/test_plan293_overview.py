"""Plan 293 F3 — Estado enriquecido del repositorio, y F4 — el semaforo.

Los tests corren contra repositorios git DE VERDAD creados en un temporal: el
comportamiento de git ES lo que se prueba, y un doble solo probaria mi propia
idea de git. NUNCA se toca el repo de Stacky.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from services import git_workbench as gw


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, check=False)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-b", "principal")
    _git(r, "config", "user.email", "prueba@local")
    _git(r, "config", "user.name", "Prueba")
    (r / "a.txt").write_text("uno\n", encoding="utf-8")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-m", "inicial")
    return r


# ── F3: el overview ─────────────────────────────────────────────────────────
def test_01_carpeta_sin_repositorio_degrada(tmp_path):
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    r = gw.repo_overview(vacia)
    assert r["ok"] is True and r["available"] is False
    # El motivo va en castellano llano, SIN jerga: quien lo lee no sabe git.
    assert "historial de cambios" in r["reason"]
    assert "git" not in r["reason"].lower()


def test_02_repo_limpio(repo):
    r = gw.repo_overview(repo)
    assert r["available"] is True
    assert r["repo"]["branch"] == "principal"
    assert r["archivos"] == []
    assert r["conflictos"] == []


def test_03_index_lock_presente_degrada(repo):
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")
    r = gw.repo_overview(repo)
    assert r["available"] is False
    assert "otra" in r["reason"].lower()


def test_04_rama_sin_upstream(repo):
    r = gw.repo_overview(repo)
    assert r["repo"]["upstream"] is None
    assert r["repo"]["ahead"] == 0 and r["repo"]["behind"] == 0


def test_05_modificado_y_sin_seguimiento(repo):
    (repo / "a.txt").write_text("dos\n", encoding="utf-8")
    (repo / "nuevo.txt").write_text("x\n", encoding="utf-8")
    r = gw.repo_overview(repo)
    rutas = {a["path"]: a for a in r["archivos"]}
    assert rutas["a.txt"]["grupo"] == "modificados"
    assert rutas["nuevo.txt"]["grupo"] == "sin_seguimiento"


def test_06_borrado(repo):
    (repo / "a.txt").unlink()
    r = gw.repo_overview(repo)
    assert any(a["path"] == "a.txt" and a["grupo"] == "borrados" for a in r["archivos"])


def test_07_conflicto_aparece_en_conflictos(repo):
    """Un conflicto real: dos ramas tocan la misma linea y se fusionan."""
    _git(repo, "switch", "-c", "otra")
    (repo / "a.txt").write_text("rama otra\n", encoding="utf-8")
    _git(repo, "commit", "-am", "otra")
    _git(repo, "switch", "principal")
    (repo / "a.txt").write_text("rama principal\n", encoding="utf-8")
    _git(repo, "commit", "-am", "principal")
    _git(repo, "merge", "otra")  # deja el conflicto en el arbol

    r = gw.repo_overview(repo)
    assert "a.txt" in r["conflictos"], f"conflicto no detectado: {r}"
    assert any(a["path"] == "a.txt" and a["grupo"] == "conflictos" for a in r["archivos"])


def test_08_renombrado(repo):
    _git(repo, "mv", "a.txt", "b.txt")
    r = gw.repo_overview(repo)
    assert any(a["grupo"] == "renombrados" for a in r["archivos"]), r["archivos"]


def test_09_ruta_con_espacios(repo):
    destino = repo / "con espacios.txt"
    destino.write_text("x\n", encoding="utf-8")
    r = gw.repo_overview(repo)
    assert any(a["path"] == "con espacios.txt" for a in r["archivos"]), r["archivos"]


def test_10_identidad_git_presente(repo):
    assert gw.repo_overview(repo)["identidad_ok"] is True


def test_11_identidad_git_ausente(tmp_path, monkeypatch):
    """Sin identidad, `git commit` falla con un texto largo y en ingles. El
    tablero tiene que detectarlo ANTES de ofrecer el boton.

    Hay que aislar la config GLOBAL del operador: un `--unset` local no alcanza
    porque git cae a la global y la encuentra.
    """
    r = tmp_path / "sinid"
    r.mkdir()
    _git(r, "init", "-b", "principal")
    vacia = tmp_path / "gitconfig-vacio"
    vacia.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(vacia))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(vacia))

    ov = gw.repo_overview(r)
    assert ov["available"] is True
    assert ov["identidad_ok"] is False


def test_12_porcelain_v1_NO_trae_la_rama(repo):
    """Mitad de contraste de la decision de usar v2: si v1 alcanzara, F3 no
    haria falta. Se prueba que NO alcanza."""
    v1 = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=str(repo),
        capture_output=True, text=True, check=False,
    ).stdout
    assert "branch.head" not in v1
    v2 = subprocess.run(
        ["git", "status", "--porcelain=v2", "--branch"], cwd=str(repo),
        capture_output=True, text=True, check=False,
    ).stdout
    assert "branch.head" in v2


@pytest.mark.parametrize(
    "xy,esperado",
    [
        # Los conflictos van PRIMERO. Clasificar por `in` los disfraza: "AA"
        # contiene "A" y saldria como nuevo, "DD" contiene "D" y saldria como
        # borrado. Es el mismo defecto que F5 cierra en el frontend.
        ("DD", "conflictos"), ("AA", "conflictos"), ("UU", "conflictos"),
        ("AU", "conflictos"), ("UA", "conflictos"), ("DU", "conflictos"), ("UD", "conflictos"),
        ("R.", "renombrados"), (".R", "renombrados"),
        (".D", "borrados"), ("A.", "nuevos"), (".M", "modificados"), ("MM", "modificados"),
        ("XY", "otros"),
    ],
)
def test_13_clasificacion_por_par_xy(xy, esperado):
    """Unidad de `_grupo_de`. Existe porque en porcelain v2 los conflictos llegan
    como lineas `u` y NO pasan por esta funcion: sin este caso, su rama de
    conflictos seria codigo que ningun test puede poner rojo, o sea un adorno."""
    assert gw._grupo_de(xy) == esperado


# ── F4: el semaforo ─────────────────────────────────────────────────────────
_REPO_OK = {
    "available": True,
    "conflictos": [],
    "archivos": [{"path": "a.txt", "grupo": "modificados"}],
    "identidad_ok": True,
    "repo": {"upstream": "origin/principal"},
}
_FLAGS_TODO = {"escritura": True, "envio": True}


def _codigos(res):
    return [b["codigo"] for b in res["bloqueos"]]


def test_20_sin_bloqueos_puede():
    r = gw.evaluar_operacion(repo=_REPO_OK, accion="confirmar", flags=_FLAGS_TODO, seleccion=["a.txt"])
    assert r["puede"] is True and r["bloqueos"] == []


def test_21_repo_no_disponible():
    repo = {**_REPO_OK, "available": False}
    r = gw.evaluar_operacion(repo=repo, accion="confirmar", flags=_FLAGS_TODO, seleccion=["a.txt"])
    assert "repo_no_disponible" in _codigos(r) and r["puede"] is False


def test_22_conflictos_presentes():
    repo = {**_REPO_OK, "conflictos": ["a.txt"]}
    r = gw.evaluar_operacion(repo=repo, accion="confirmar", flags=_FLAGS_TODO, seleccion=["a.txt"])
    assert "conflictos_presentes" in _codigos(r)


def test_23_sin_cambios():
    repo = {**_REPO_OK, "archivos": []}
    r = gw.evaluar_operacion(repo=repo, accion="confirmar", flags=_FLAGS_TODO, seleccion=[])
    assert "sin_cambios" in _codigos(r)


def test_24_nada_seleccionado():
    r = gw.evaluar_operacion(repo=_REPO_OK, accion="confirmar", flags=_FLAGS_TODO, seleccion=[])
    assert "nada_seleccionado" in _codigos(r)


def test_25_escritura_apagada():
    r = gw.evaluar_operacion(
        repo=_REPO_OK, accion="confirmar",
        flags={"escritura": False, "envio": True}, seleccion=["a.txt"],
    )
    assert "escritura_apagada" in _codigos(r)


def test_26_push_apagado():
    r = gw.evaluar_operacion(
        repo=_REPO_OK, accion="enviar",
        flags={"escritura": True, "envio": False}, seleccion=[],
    )
    assert "push_apagado" in _codigos(r)


def test_27_sin_identidad_avisa_pero_NO_bloquea():
    """PROBADO ejecutando: `git commit` SIN user.email NO falla — git deriva la
    identidad de usuario+host y commitea con exit 0. Bloquear por la sonda
    `config --get user.email` (que si sale con exit 1) seria un FALSO BLOQUEO
    permanente en cualquier maquina sin identidad explicita."""
    repo = {**_REPO_OK, "identidad_ok": False}
    r = gw.evaluar_operacion(repo=repo, accion="confirmar", flags=_FLAGS_TODO, seleccion=["a.txt"])
    assert "identidad_derivada" in [a["codigo"] for a in r["avisos"]]
    assert r["puede"] is True


@pytest.mark.parametrize("marca,esperado", [
    ("MERGE_HEAD", "fusion"),
    ("CHERRY_PICK_HEAD", "copia_de_cambio"),
    ("REVERT_HEAD", "reversion"),
])
def test_27b_operacion_a_medias_detectada_en_el_disco(repo, marca, esperado):
    """PROBADO ejecutando: con una fusion a medias, `git commit -F m -- <ruta>`
    muere con `fatal: cannot do a partial commit during a merge` (exit 128).
    Y apenas el usuario resuelve el conflicto con `add`, las lineas `u`
    DESAPARECEN del status: el sensor elegido NO lo ve. Solo se ve en el disco."""
    (repo / ".git" / marca).write_text("deadbeef\n", encoding="utf-8")
    assert gw.operacion_en_curso(repo) == esperado
    ov = gw.repo_overview(repo)
    assert ov["operacion_en_curso"] == esperado


def test_27c_operacion_a_medias_bloquea_el_confirmar():
    repo = {**_REPO_OK, "operacion_en_curso": "fusion"}
    r = gw.evaluar_operacion(repo=repo, accion="confirmar", flags=_FLAGS_TODO, seleccion=["a.txt"])
    assert "operacion_en_curso" in _codigos(r)
    assert r["puede"] is False


def test_27d_el_status_NO_delata_la_fusion_resuelta(repo):
    """La razon de ser de la sonda por disco, medida."""
    _git(repo, "switch", "-c", "otra")
    (repo / "a.txt").write_text("otra\n", encoding="utf-8")
    _git(repo, "commit", "-am", "otra")
    _git(repo, "switch", "principal")
    (repo / "a.txt").write_text("principal\n", encoding="utf-8")
    _git(repo, "commit", "-am", "principal")
    _git(repo, "merge", "otra")
    _git(repo, "add", "a.txt")          # el usuario "resuelve" el conflicto

    ov = gw.repo_overview(repo)
    assert ov["conflictos"] == [], "el status ya no muestra el conflicto"
    assert ov["operacion_en_curso"] == "fusion", "pero la fusion SIGUE en curso"


def test_28_aviso_de_cambios_no_seleccionados():
    """El aviso que evita el robo silencioso: hay 2 archivos y elegiste 1."""
    repo = {**_REPO_OK, "archivos": [
        {"path": "a.txt", "grupo": "modificados"},
        {"path": "ajeno.txt", "grupo": "modificados"},
    ]}
    r = gw.evaluar_operacion(repo=repo, accion="confirmar", flags=_FLAGS_TODO, seleccion=["a.txt"])
    assert "hay_cambios_no_seleccionados" in [a["codigo"] for a in r["avisos"]]
    assert r["puede"] is True  # es aviso, NO bloqueo


def test_29_aviso_rama_sin_upstream():
    repo = {**_REPO_OK, "repo": {"upstream": None}}
    r = gw.evaluar_operacion(repo=repo, accion="confirmar", flags=_FLAGS_TODO, seleccion=["a.txt"])
    assert "rama_sin_upstream" in [a["codigo"] for a in r["avisos"]]


def test_30_bloqueos_acumulables():
    """No devuelve el primero que encuentra: devuelve TODOS. Devolver uno solo
    obliga al usuario a descubrir los otros de a uno."""
    repo = {**_REPO_OK, "conflictos": ["x"], "operacion_en_curso": "fusion"}
    r = gw.evaluar_operacion(
        repo=repo, accion="confirmar",
        flags={"escritura": False, "envio": False}, seleccion=[],
    )
    for esperado in ("conflictos_presentes", "operacion_en_curso", "escritura_apagada", "nada_seleccionado"):
        assert esperado in _codigos(r), f"falta {esperado} en {_codigos(r)}"


def test_31_orden_estable():
    repo = {**_REPO_OK, "conflictos": ["x"], "identidad_ok": False}
    a = gw.evaluar_operacion(repo=repo, accion="confirmar", flags=_FLAGS_TODO, seleccion=[])
    b = gw.evaluar_operacion(repo=repo, accion="confirmar", flags=_FLAGS_TODO, seleccion=[])
    assert _codigos(a) == _codigos(b)


def test_32_todos_los_codigos_estan_declarados():
    """El catalogo de codigos es CERRADO: si aparece uno que no esta declarado,
    F12 no tiene traduccion para el y el operador ve un codigo crudo."""
    repo = {**_REPO_OK, "available": False, "conflictos": ["x"], "identidad_ok": False, "archivos": []}
    for accion in ("confirmar", "enviar", "traer", "cambiar_rama"):
        r = gw.evaluar_operacion(
            repo=repo, accion=accion,
            flags={"escritura": False, "envio": False}, seleccion=[],
        )
        for b in r["bloqueos"]:
            assert b["codigo"] in gw.CODIGOS_BLOQUEO, f"{b['codigo']} no declarado"
        for a in r["avisos"]:
            assert a["codigo"] in gw.CODIGOS_AVISO, f"{a['codigo']} no declarado"


def test_33_el_semaforo_es_puro():
    """Sin Flask, sin api/, sin base: testeable sin app."""
    import inspect
    fuente = inspect.getsource(gw.evaluar_operacion)
    for prohibido in ("flask", "from api", "import api", "session", "request"):
        assert prohibido not in fuente.lower()
