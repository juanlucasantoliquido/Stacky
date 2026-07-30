# backend/tests/test_plan271_censo_escritores.py
"""Plan 271 F8 — Censo ejecutable de escritores de estado de un work item.

AST, nunca regex (un ast.Call no puede confundir prosa con código). Recorre
TODO `backend/` (excluyendo tests/.venv/venv/__pycache__), marca llamadas a
`update_item_state`/`update_work_item_state`/`_safe_transition` Y las
DEFINICIONES de `update_item_state`/`update_work_item_state` (regla ampliada
v4/E6: sin esto el censo es ciego al adaptador GitLab).

13 entradas — [v5, E19]: los 6 motores (A..F) + 2 helpers del plan 79 + el
Protocol del puerto + 2 adaptadores + el cliente terminal de ADO + el router
del plan 270. Re-correr el Paso 0 el día de la implementación: el número
CADUCA con cada merge ajeno (D1, E19 — cuarta vez que sube entre versiones).
"""
from __future__ import annotations

import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent
ATTRS = {"update_item_state", "update_work_item_state"}


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel = rel
        self.stack: list[str] = []
        self.hits: list[tuple[str, int, str]] = []

    def visit_FunctionDef(self, node):  # noqa: N802
        self.stack.append(node.name)
        if node.name in ATTRS:  # E6 — la DEFINICIÓN también cuenta
            self.hits.append((f"{self.rel}::{node.name}", node.lineno, "def " + node.name))
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):  # noqa: N802
        f, name = node.func, None
        if isinstance(f, ast.Attribute) and f.attr in ATTRS:
            name = f.attr
        elif isinstance(f, ast.Attribute) and f.attr == "_safe_transition":
            name = "_safe_transition"
        elif isinstance(f, ast.Name) and f.id == "_safe_transition":
            name = "_safe_transition"
        if name:
            cont = self.stack[-1] if self.stack else "<module>"
            self.hits.append((f"{self.rel}::{cont}", node.lineno, name))
        self.generic_visit(node)


def _censo() -> dict[str, list[tuple[int, str]]]:
    agg: dict[str, list[tuple[int, str]]] = {}
    for p in BACKEND.rglob("*.py"):
        s = p.as_posix()
        if any(x in s for x in ("/tests/", "/.venv/", "/venv/", "__pycache__")):
            continue
        rel = p.relative_to(BACKEND).as_posix()
        v = _Visitor(rel)
        v.visit(ast.parse(p.read_text(encoding="utf-8")))
        for key, lineno, name in v.hits:
            agg.setdefault(key, []).append((lineno, name))
    return agg


# 13 entradas [v5, E19] = los SEIS motores de §2.1 (A..F) + los dos helpers del
# plan 79 + los DOS adaptadores + el Protocol del puerto + el cliente terminal
# de ADO + el router del plan 270. Re-corrido el día de esta implementación:
# sigue en 13 (byte-idéntico a lo que documenta la v7).
ESCRITORES_CENSADOS: dict[str, str] = {
    # ── escritor canónico y helper de arranque (plan 79) ────────────────────
    "harness/task_states.py::_safe_transition": "plan 79 — el escritor canónico (lo usan A, B y C)",
    "harness/task_states.py::apply_task_start_state": "plan 79 — estado al INICIAR (fuera del alcance del 271)",
    # ── los SEIS motores ───────────────────────────────────────────────────
    "services/completion_state.py::maybe_apply_state_transition": "MOTOR A — plan 208 + 271 F2/F2-bis",
    "services/agent_completion_internal.py::_attempt_state_change": "MOTOR B — plan 271 F3/F3-bis-2",
    "api/tickets.py::_apply_task_state": "MOTOR C — plan 79 + gate del 210 (el 271 NO lo modifica, §6.6)",
    "api/tickets.py::set_stacky_status_by_ado": "MOTOR D — inline, ya parcialmente ruteado por el plan 270 vía tracker_write_router (el 271 NO lo modifica; unificación en el 272)",
    "api/tickets.py::finish_work": "MOTOR E — inline, ídem D (el v2 lo citó en §6.6 y NO lo censó; 272)",
    "api/tickets.py::create_child_task": "MOTOR F — estado de la TAREA HIJA recién creada, sin plan dueño (272)",
    # ── puerto, adaptadores y cliente terminal (E6): NO deciden, pero SÍ escriben ──
    "services/tracker_provider.py::update_item_state": "PUERTO — Protocol (cuerpo `...`); acá para que un tracker nuevo no entre invisible",
    "services/ado_provider.py::update_item_state": "ADAPTADOR ADO → AdoClient.update_work_item_state",
    "services/gitlab_provider.py::update_item_state": "ADAPTADOR GitLab → label de estado + cierre del issue (el v3 NO lo veía)",
    "services/ado_client.py::update_work_item_state": "CLIENTE TERMINAL ADO — el PATCH real de System.State (nadie lo había censado nunca)",
    # ── [v5, E19] agregado por el plan 270, mergeado DESPUÉS del commit base ──
    "services/tracker_write_router.py::write_state_for_ticket": "ROUTER — plan 270, resuelve ADO/GitLab para set_stacky_status_by_ado y ticket_state_writeback.py (ver §3.5 sobre F3 y este mismo router)",
}


def test_1_censo_sin_escritor_nuevo_sin_censar():
    hallados = set(_censo())
    censados = set(ESCRITORES_CENSADOS)
    nuevos = hallados - censados
    assert nuevos == set(), (
        f"Escritor de estado NUEVO sin censar: {sorted(nuevos)}. "
        "Agregalo al censo con su plan dueño, o rutealo por `_safe_transition`."
    )


def test_2_censo_sin_entrada_fantasma():
    hallados = set(_censo())
    censados = set(ESCRITORES_CENSADOS)
    fantasmas = censados - hallados
    assert fantasmas == set(), (
        f"Escritor censado que ya no existe: {sorted(fantasmas)}. Sacalo del censo."
    )


def test_3_completion_state_importa_dev_build_verify():
    """Invariante concreto de C2: si alguien vuelve a sacar el gate de build del
    motor A (F2-bis guardia 1), este test se pone rojo con el nombre del plan
    que se rompe (210)."""
    src = (BACKEND / "services" / "completion_state.py").read_text(encoding="utf-8")
    assert "dev_build_verify" in src, (
        "services/completion_state.py dejó de importar dev_build_verify: "
        "el gate de build del plan 210 (F2-bis guardia 1) se rompió."
    )
