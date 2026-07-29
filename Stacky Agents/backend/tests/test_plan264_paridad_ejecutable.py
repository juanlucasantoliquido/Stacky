"""Plan 264 F2.5 — centinelas ejecutables: que el bug no pueda volver.

El bug de Codex (F2) no fue "alguien se olvidó una línea": fue que NADA en el
sistema podía detectar (a) un parámetro de selección aceptado y jamás
consumido, (b) uno consumido SIN efecto, ni (c) una corrección aplicada a una
rama MUERTA. Estos tests instalan los tres candados + el contrato por runtime
+ el gate del binding de `config` (C2). No hay código de producción nuevo acá:
es puro gate.

[FIX C6 v4→v5] F5.5 agrega el Test F a este MISMO archivo (cadena
DocsPage → Documentador); ver más abajo.
"""
from __future__ import annotations

import ast
import inspect
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import config  # noqa: E402


# ---------------------------------------------------------------------------
# Test A — cero parámetros decorativos (AST, KPI-6)
# ---------------------------------------------------------------------------

def _iter_functions_matching(pattern: str, py_files: list[Path]):
    rx = re.compile(pattern)
    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and rx.match(node.name):
                yield path, node


def _metadata_dict_subtree_lines(func_node: ast.FunctionDef) -> set[int]:
    """Líneas cubiertas por cada Dict literal asignado a `*.metadata_dict`
    dentro de esta función — para no contar ESE uso como "consumo real"."""
    lines: set[int] = set()
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign):
            targets_metadata = any(
                isinstance(t, ast.Attribute) and t.attr == "metadata_dict"
                for t in node.targets
            )
            if targets_metadata and isinstance(node.value, ast.Dict):
                for sub in ast.walk(node.value):
                    if hasattr(sub, "lineno"):
                        lines.add(sub.lineno)
    return lines


def test_a_no_decorative_selection_params():
    """Para cada start_*_run: si acepta effort_override/model_override, su
    ÚNICO uso no puede ser el metadata_dict (eso es exactamente lo que hacía
    el bug: aceptado y nunca materializado en la corrida real)."""
    runner_files = sorted((ROOT / "services").glob("*_runner.py"))
    checked = 0
    for path, func in _iter_functions_matching(r"^start_.*_run$", runner_files):
        param_names = {a.arg for a in func.args.args} | {a.arg for a in func.args.kwonlyargs}
        for param in ("effort_override", "model_override"):
            if param not in param_names:
                continue
            checked += 1
            meta_lines = _metadata_dict_subtree_lines(func)
            usos_fuera = [
                node.lineno for node in ast.walk(func)
                if isinstance(node, ast.Name) and node.id == param
                and node.lineno not in meta_lines
            ]
            assert usos_fuera, (
                f"{path.name}::{func.name}: '{param}' está declarado pero su "
                f"único uso (si hubo alguno) fue el metadata_dict — decorativo"
            )
    assert checked >= 2, "no se encontraron start_*_run con estos parámetros — el test no probó nada"


def test_a_fix_c1_agent_runner_calls_pass_both_kwargs():
    """[FIX C1] Las CUATRO llamadas a start_*_run en agent_runner.py (rama
    viva :442/:456 y rama muerta :256/:335) pasan AMBOS overrides. Control
    negativo (§10): revertir a mano las dos líneas 'effort_override=
    effort_override,' debe poner esto en rojo en exactamente 2 de las 4."""
    tree = ast.parse((ROOT / "agent_runner.py").read_text(encoding="utf-8"), filename="agent_runner.py")
    target_names = {"start_codex_cli_run", "start_claude_code_cli_run"}
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in target_names:
                calls.append(node)

    assert len(calls) == 4, f"esperaba 4 llamadas a start_*_run en agent_runner.py, hay {len(calls)}"
    faltantes = []
    for call in calls:
        kw_names = {kw.arg for kw in call.keywords}
        if "model_override" not in kw_names:
            faltantes.append(f"línea {call.lineno}: falta model_override")
        if "effort_override" not in kw_names:
            faltantes.append(f"línea {call.lineno}: falta effort_override")
    assert faltantes == [], "\n".join(faltantes)


# ---------------------------------------------------------------------------
# Test B — contrato de honra, parametrizado por RUNTIMES
# ---------------------------------------------------------------------------

def test_b_contrato_de_honra_por_runtime():
    from services import runtime_capabilities as rc
    from services.claude_code_cli_runner import start_claude_code_cli_run
    from services.codex_cli_runner import start_codex_cli_run

    runner_by_runtime = {
        "codex_cli": start_codex_cli_run,
        "claude_code_cli": start_claude_code_cli_run,
    }
    for runtime in rc.RUNTIMES:
        caps = rc.capabilities_for(runtime)
        if caps["supports_effort"]:
            assert rc.EFFORT_MODE[runtime] in ("nativo", "presupuesto_turnos"), runtime
            runner = runner_by_runtime.get(runtime)
            if runner is not None:
                assert "effort_override" in inspect.signature(runner).parameters, (
                    f"{runtime}: soporta effort pero su runner no acepta effort_override"
                )
            assert caps["efforts"], f"{runtime}: efforts vacío pese a supports_effort=True"
        else:
            assert rc.EFFORT_MODE[runtime] == "no_aplica", runtime
            assert caps["efforts"] == [], runtime
            assert caps["effort_note"], f"{runtime}: sin nota que explique por qué no hay selector"


# ---------------------------------------------------------------------------
# Test C — anti-regresión del cap (propiedad, no ejemplo)
# ---------------------------------------------------------------------------

def test_c_anti_regresion_del_cap():
    from services.runtime_capabilities import EFFORTS, codex_turn_budget

    for cap in (0, 1, 5, 40):
        for e in EFFORTS:
            assert codex_turn_budget(e, cap) <= max(cap, 0), (e, cap)
    for e in EFFORTS:
        assert codex_turn_budget(e, 0) == 0, e


# ---------------------------------------------------------------------------
# Test D — [ADICIÓN ARQUITECTO] efecto observable, no consumo simbólico
# ---------------------------------------------------------------------------

def test_d_efecto_observable_no_consumo_simbolico(monkeypatch):
    from services.runtime_capabilities import capabilities_for, codex_turn_budget

    monkeypatch.setattr(config.config, "STACKY_RUNAWAY_MAX_TURNS", 40)
    assert codex_turn_budget("low", 40) != codex_turn_budget("max", 40)

    monkeypatch.setattr(config.config, "STACKY_RUNAWAY_MAX_TURNS", 0)
    assert codex_turn_budget("low", 0) == codex_turn_budget("max", 0)
    assert capabilities_for("codex_cli")["effort_effective_now"] is False, (
        "la inercia con cap=0 debe estar DECLARADA, no escondida"
    )

    # claude_code_cli: el effort aparece en el comando construido (función
    # PURA — nunca lanza un CLI real).
    from services.claude_code_cli_runner import _build_command

    cmd_low = _build_command(model_override=None, effort_override="low")
    cmd_max = _build_command(model_override=None, effort_override="max")
    assert cmd_low != cmd_max
    assert "low" in cmd_low and "max" not in cmd_low
    assert "max" in cmd_max and "low" not in cmd_max


# ---------------------------------------------------------------------------
# Test E — [ADICIÓN ARQUITECTO] gate AST del binding de `config` (§3.8)
# ---------------------------------------------------------------------------

_CONFIG_BINDING_SCOPE = [
    "agent_runner.py",
    "services/codex_cli_runner.py",
    "services/claude_code_cli_runner.py",
    "services/runtime_capabilities.py",
    "api/agents.py",
    "api/devops_agent.py",
    "api/devops_remote_console.py",
    "api/preferences.py",
    "api/plans_board.py",
    "services/adaptive_selector.py",
]


def _config_binding(tree: ast.AST) -> tuple[str, str] | None:
    """Primer import de `config` en TODO el archivo (a cualquier profundidad,
    incluidos imports dentro de funciones). Devuelve (kind, local_name):
    kind="instance" -> `from config import config [as X]` (X YA es la instancia)
    kind="module"   -> `import config [as X]` (X es el MÓDULO)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "config":
            for alias in node.names:
                if alias.name == "config":
                    return ("instance", alias.asname or "config")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "config":
                    return ("module", alias.asname or "config")
    return None


def test_e_config_binding_gate():
    from services.harness_flags import FLAG_REGISTRY

    flag_keys = {s.key for s in FLAG_REGISTRY}
    violations: list[str] = []

    for rel_path in _CONFIG_BINDING_SCOPE:
        path = ROOT / rel_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        binding = _config_binding(tree)
        if binding is None:
            continue  # el archivo no importa config: nada que chequear
        kind, local_name = binding

        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if kind == "instance":
                # <local_name>.config.<algo> está MAL: local_name YA es la instancia.
                if (
                    isinstance(node.value, ast.Attribute)
                    and node.value.attr == "config"
                    and isinstance(node.value.value, ast.Name)
                    and node.value.value.id == local_name
                ):
                    violations.append(
                        f"{rel_path}:{node.lineno}: binding es 'from config import "
                        f"config as {local_name}' (instancia) -> '{local_name}.config."
                        f"{node.attr}' está mal; usar getattr({local_name}, "
                        f"'{node.attr}', default)"
                    )
            else:  # kind == "module"
                # <local_name>.<KEY> está MAL si KEY es una flag real: hay que
                # pasar por `.config` para llegar a la instancia.
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id == local_name
                    and node.attr in flag_keys
                ):
                    violations.append(
                        f"{rel_path}:{node.lineno}: binding es 'import config as "
                        f"{local_name}' (módulo) -> '{local_name}.{node.attr}' está "
                        f"mal; usar {local_name}.config.{node.attr}"
                    )

    assert violations == [], "\n".join(violations)


# ---------------------------------------------------------------------------
# F5.5 [FIX C6 v4→v5] — Test F: el picker de DocsPage no queda huérfano
# ---------------------------------------------------------------------------
#
# La cadena confirmada end-to-end (v4→v5, C6):
#   DocsPage.tsx:handleProposeUpdate -> Docs.stalenessFix
#   -> POST /api/docs/staleness/fix -> api/docs.py:staleness_fix()
#   -> doc_documenter.start_documenter_run(...)
#   -> (thread) _run_documenter_thread -> run_documenter -> invoke_documenter
#   -> agent_runner.run_agent(agent_type="Documentador", ...)
#
# Medido en el código real: run_agent NO se llama directo dentro de
# start_documenter_run — hay TRES saltos de indirección (thread + 2 llamadas
# internas) antes de llegar a invoke_documenter, que es quien de verdad
# invoca run_agent (services/doc_documenter.py:385). El Test F verifica la
# cadena COMPLETA, función por función, no sólo el primer eslabón.

@pytest.fixture
def _docs_client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setattr(config.config, "STACKY_DOCS_STALENESS_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_ENABLED", True)

    from app import create_app
    from services import run_slots
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    run_slots._reset_for_tests()
    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()
    run_slots._reset_for_tests()


def test_f_docspage_picker_invokes_start_documenter_run(_docs_client, monkeypatch):
    """Pasos 1-3 del Test F: mock de start_documenter_run + POST real +
    afirmar invocación con only_note == note_path del body."""
    from unittest.mock import MagicMock

    mock_start = MagicMock(return_value="run-plan264-test")
    monkeypatch.setattr(
        "services.doc_documenter.start_documenter_run", mock_start
    )

    resp = _docs_client.post(
        "/api/docs/staleness/fix",
        json={"note_path": "docs/sistema/algo.md", "project": "RSPacifico"},
    )

    assert resp.status_code == 200, resp.get_json()
    mock_start.assert_called_once()
    assert mock_start.call_args.kwargs["only_note"] == "docs/sistema/algo.md"


def test_f_docspage_documentador_chain_not_orphaned_static():
    """Paso 4 del Test F: AST función por función de la cadena REAL
    (start_documenter_run -> _run_documenter_thread -> run_documenter ->
    invoke_documenter -> run_agent). Control negativo (§10): comentar a mano
    la línea `agent_runner.run_agent(` dentro de invoke_documenter (o
    reemplazar el target del Thread) debe poner esto en rojo."""
    path = ROOT / "services" / "doc_documenter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

    for name in ("start_documenter_run", "_run_documenter_thread", "run_documenter", "invoke_documenter"):
        assert name in funcs, f"la cadena perdió la función {name}"

    def _references(func_node: ast.FunctionDef, target_name: str) -> bool:
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
                if name == target_name:
                    return True
            # threading.Thread(target=_run_documenter_thread, ...) referencia
            # el símbolo como valor, no como Call.
            if isinstance(node, ast.Name) and node.id == target_name:
                return True
        return False

    assert _references(funcs["start_documenter_run"], "_run_documenter_thread"), (
        "start_documenter_run ya no lanza _run_documenter_thread — el picker de "
        "DocsPage quedaría sin lanzar nada"
    )
    assert _references(funcs["_run_documenter_thread"], "run_documenter"), (
        "_run_documenter_thread ya no llama a run_documenter"
    )
    assert _references(funcs["run_documenter"], "invoke_documenter"), (
        "run_documenter ya no llama a invoke_documenter"
    )
    assert _references(funcs["invoke_documenter"], "run_agent"), (
        "invoke_documenter ya no llama a run_agent — la cadena quedó huérfana"
    )
