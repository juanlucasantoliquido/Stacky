"""Plan 293 F7 — Traer cambios, con la politica como PARAMETRO.

EL SUPUESTO DE CAPACIDAD QUE ESTA FASE MATA
-------------------------------------------
`run_pull_check` lee la politica de config (services/pre_run_git.py:102) y el
bloque que fusiona solo corre con "ff_only_block_on_dirty". El valor de fabrica
es "fetch_only_warn" (config.py:865-866). O sea: un boton "Traer cambios" que
llamara a `run_pull_check` tal como estaba haria `fetch` y NO BAJARIA NADA, en
verde, sin que ningun test lo notara.

`merge --ff-only` es el unico verbo de fusion y no puede perder trabajo: ante
divergencia FALLA, no fusiona.
"""
from __future__ import annotations

import inspect

import pytest

from services import pre_run_git
from services.pre_run_git import GitStep, run_pull_check


class _Grabador:
    """Sustituye a _run_git y anota que comandos se pidieron."""

    def __init__(self, *, sucio: bool = False, upstream: str | None = "origin/principal"):
        self.comandos: list[list[str]] = []
        self.sucio = sucio
        self.upstream = upstream

    def __call__(self, cwd, args, timeout_seconds, *, auth_header=None):
        self.comandos.append(list(args))
        verbo = args[0]
        if verbo == "rev-parse" and "--show-toplevel" in args:
            return GitStep(name=verbo, ok=True, command=args, stdout=str(cwd))
        if verbo == "rev-parse" and "@{u}" in args:
            if self.upstream is None:
                return GitStep(name=verbo, ok=False, command=args, stderr="no upstream")
            return GitStep(name=verbo, ok=True, command=args, stdout=self.upstream)
        if verbo == "rev-parse":
            return GitStep(name=verbo, ok=True, command=args, stdout="principal")
        if verbo == "status":
            return GitStep(name=verbo, ok=True, command=args, stdout=" M a.txt" if self.sucio else "")
        return GitStep(name=verbo, ok=True, command=args, stdout="")

    @property
    def verbos(self) -> list[str]:
        return [c[0] for c in self.comandos]


@pytest.fixture()
def grabador(monkeypatch, tmp_path):
    g = _Grabador()
    monkeypatch.setattr(pre_run_git, "_run_git", g)
    return g


def _correr(tmp_path, **kw):
    return run_pull_check(str(tmp_path), enabled=True, required=False, fetch=True, **kw)


# ── La politica como parametro ──────────────────────────────────────────────
def test_01_sin_policy_lee_la_config_fetch_only(monkeypatch, grabador, tmp_path):
    from config import config
    monkeypatch.setattr(config, "STACKY_PRE_RUN_GIT_WORKSPACE_POLICY", "fetch_only_warn")
    res = _correr(tmp_path)
    assert res.policy == "fetch_only_warn"
    assert "merge" not in grabador.verbos, "con la politica de fabrica NO se fusiona"


def test_02_sin_policy_lee_la_config_bloqueante(monkeypatch, grabador, tmp_path):
    from config import config
    monkeypatch.setattr(config, "STACKY_PRE_RUN_GIT_WORKSPACE_POLICY", "ff_only_block_on_dirty")
    res = _correr(tmp_path)
    assert res.policy == "ff_only_block_on_dirty"
    assert "merge" in grabador.verbos


def test_03_policy_explicita_GANA_sobre_la_config(monkeypatch, grabador, tmp_path):
    """EL caso de la fase: la config del operador dice fetch_only_warn (el valor
    de fabrica) y el tablero igual necesita fusionar."""
    from config import config
    monkeypatch.setattr(config, "STACKY_PRE_RUN_GIT_WORKSPACE_POLICY", "fetch_only_warn")
    res = _correr(tmp_path, policy="ff_only_block_on_dirty")
    assert res.policy == "ff_only_block_on_dirty"
    assert "merge" in grabador.verbos, "el parametro no llego al bloque de fusion"
    idx = grabador.verbos.index("merge")
    assert "--ff-only" in grabador.comandos[idx], "la fusion tiene que ser --ff-only"


def test_04_arbol_sucio_con_politica_bloqueante_no_fusiona(monkeypatch, tmp_path):
    g = _Grabador(sucio=True)
    monkeypatch.setattr(pre_run_git, "_run_git", g)
    res = run_pull_check(
        str(tmp_path), enabled=True, required=True, fetch=True,
        policy="ff_only_block_on_dirty",
    )
    assert res.ok is False
    assert "merge" not in g.verbos, "se fusiono con el arbol sucio"


def test_05_sin_upstream_no_fusiona(monkeypatch, tmp_path):
    g = _Grabador(upstream=None)
    monkeypatch.setattr(pre_run_git, "_run_git", g)
    res = run_pull_check(
        str(tmp_path), enabled=True, required=False, fetch=True,
        policy="ff_only_block_on_dirty",
    )
    assert res.upstream is None
    assert "merge" not in g.verbos


def test_06_la_fusion_NUNCA_es_forzada(monkeypatch, grabador, tmp_path):
    _correr(tmp_path, policy="ff_only_block_on_dirty")
    planos = [tok for c in grabador.comandos for tok in c]
    for prohibido in ("--force", "-f", "--no-ff", "--strategy", "-X"):
        assert prohibido not in planos, f"apareció {prohibido} en {grabador.comandos}"


# ── Retrocompatibilidad de los CINCO llamadores de produccion ───────────────
_LLAMADORES = (
    "agent_runner.py:627",                 # OJO: en la RAIZ de backend/, no en services/
    "api/diag.py:737",
    "services/claude_code_cli_runner.py:3085",
    "services/codex_cli_runner.py:1904",
    "services/memory_validator.py:497",
)


def test_07_la_firma_no_rompe_a_los_llamadores_posicionales():
    """Los 5 llamadores pasan `workspace_root` posicional y el resto por nombre.
    Si `policy` se cuela ANTES de un parametro existente, se rompen todos en
    silencio. Se verifica por FIRMA, que es ejecutable, en vez de "correr los
    llamadores", que no es un test."""
    firma = inspect.signature(run_pull_check)
    params = list(firma.parameters)
    assert "policy" in params, "policy no existe: el boton no fusionaria nada"
    assert firma.parameters["policy"].default is None
    # Todo lo que sigue a `workspace_root` es keyword-only: nadie puede romperse
    # por posicion.
    for nombre in params[1:]:
        assert firma.parameters[nombre].kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{nombre} no es keyword-only: un llamador posicional puede romperse"
        )
    assert params[0] == "workspace_root"


def test_08_llamar_sin_policy_da_lo_mismo_que_antes(monkeypatch, tmp_path):
    """El contrato viejo, intacto: sin `policy` el resultado sale de la config."""
    from config import config
    for valor in ("fetch_only_warn", "ff_only_block_on_dirty"):
        monkeypatch.setattr(config, "STACKY_PRE_RUN_GIT_WORKSPACE_POLICY", valor)
        g = _Grabador()
        monkeypatch.setattr(pre_run_git, "_run_git", g)
        res = run_pull_check(str(tmp_path), enabled=True, required=False, fetch=True)
        assert res.policy == valor
