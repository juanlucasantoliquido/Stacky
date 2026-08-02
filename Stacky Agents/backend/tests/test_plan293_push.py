"""Plan 293 F8 — Enviar cambios al servidor, sin fuerza posible.

Los tests usan un remoto DE VERDAD (`git init --bare` en un temporal): un rechazo
por non-fast-forward es la barrera central de esta fase y un doble solo probaria
mi propia idea de como se comporta git.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from services import git_local_writer as glw
from services import git_workbench as gw


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )


@pytest.fixture()
def par(tmp_path: Path):
    """Devuelve (clon, remoto_bare). El clon ya tiene un commit propio sin enviar."""
    remoto = tmp_path / "remoto.git"
    remoto.mkdir()
    _git(remoto, "init", "--bare", "-b", "principal")

    clon = tmp_path / "clon"
    clon.mkdir()
    _git(clon, "init", "-b", "principal")
    _git(clon, "config", "user.email", "prueba@local")
    _git(clon, "config", "user.name", "Prueba")
    _git(clon, "remote", "add", "origin", str(remoto))
    (clon / "a.txt").write_text("uno\n", encoding="utf-8")
    _git(clon, "add", "a.txt")
    _git(clon, "commit", "-m", "inicial")
    return clon, remoto


@pytest.fixture(autouse=True)
def _envio_encendido(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_WORKBENCH_PUSH_ENABLED", True, raising=False)


def test_01_envio_feliz(par):
    clon, remoto = par
    res = glw.enviar_cambios(raiz=clon, rama="principal")
    assert res["ok"] is True, res
    # El remoto REAL quedo con el commit.
    assert "inicial" in _git(remoto, "log", "--format=%s").stdout


def test_02_rechazo_por_non_fast_forward_NO_se_fuerza(par):
    """LA barrera de esta fase, probada de verdad: si el remoto avanzo, git
    rechaza y el tablero NO reintenta con fuerza. Un rechazo no es un error del
    tablero: es la barrera funcionando."""
    clon, remoto = par
    glw.enviar_cambios(raiz=clon, rama="principal")

    # Otra persona empuja algo mas al remoto.
    otro = clon.parent / "otro"
    otro.mkdir()
    _git(otro, "clone", str(remoto), ".")
    _git(otro, "config", "user.email", "otro@local")
    _git(otro, "config", "user.name", "Otro")
    (otro / "b.txt").write_text("de otro\n", encoding="utf-8")
    _git(otro, "add", "b.txt")
    _git(otro, "commit", "-m", "de otro")
    _git(otro, "push", "origin", "principal")

    # Yo escribo encima sin traer lo suyo.
    (clon / "a.txt").write_text("dos\n", encoding="utf-8")
    _git(clon, "commit", "-am", "mio divergente")

    res = glw.enviar_cambios(raiz=clon, rama="principal")
    assert res["ok"] is False
    assert res["codigo"] == "envio_rechazado"
    # Y el commit del OTRO sigue en el remoto: no se piso nada.
    assert "de otro" in _git(remoto, "log", "--format=%s").stdout


def test_03_el_comando_NUNCA_lleva_fuerza(par, monkeypatch):
    clon, _ = par
    vistos: list[list[str]] = []
    original = gw._run_git

    def espia(args, cwd, **kw):
        vistos.append(list(args))
        return original(args, cwd, **kw)

    monkeypatch.setattr(gw, "_run_git", espia)
    glw.enviar_cambios(raiz=clon, rama="principal")

    planos = [t for c in vistos for t in c]
    for prohibido in ("--force", "-f", "--force-with-lease", "--mirror", "--delete"):
        assert prohibido not in planos, f"aparecio {prohibido} en {vistos}"


@pytest.mark.parametrize("rama", ["+principal", "HEAD:refs/heads/principal", "refs/heads/*:refs/heads/*"])
def test_04_una_rama_que_fuerza_no_llega_a_git(par, rama):
    """`git push origin +main` es un force-push COMPLETO sin escribir --force.
    El catalogo cerrado lo veta antes de ejecutarlo."""
    clon, remoto = par
    res = glw.enviar_cambios(raiz=clon, rama=rama)
    assert res["ok"] is False
    assert res["codigo"] == "rama_invalida"


def test_05_flag_apagada_no_corre_git(par, monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_WORKBENCH_PUSH_ENABLED", False, raising=False)
    vistos = []
    monkeypatch.setattr(gw, "_run_git", lambda *a, **k: vistos.append(a) or None)
    res = glw.enviar_cambios(raiz=par[0], rama="principal")
    assert res["ok"] is False and res["codigo"] == "push_apagado"
    assert vistos == []


def test_06_el_pat_no_aparece_en_la_respuesta(par, monkeypatch):
    """El comando que vuelve al navegador tiene que estar redactado."""
    clon, _ = par
    monkeypatch.setattr(
        glw, "_auth_para", lambda project: "Basic c3VwZXJzZWNyZXRvOnBhdA==",
    )
    res = glw.enviar_cambios(raiz=clon, rama="principal", project="X")
    texto = repr(res)
    assert "c3VwZXJzZWNyZXRvOnBhdA==" not in texto, "el PAT viajo en la respuesta"


def test_07_redactar_enmascara_el_encabezado():
    cmd = ["git", "-c", "http.extraheader=Authorization: Basic SECRETO", "push", "origin", "x"]
    assert "SECRETO" not in " ".join(gw.redactar(cmd))
    assert "<redactado>" in " ".join(gw.redactar(cmd))
