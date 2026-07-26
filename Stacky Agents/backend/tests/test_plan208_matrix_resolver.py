"""Plan 208 F1 — Resolver de matriz por (work_item_type x agent_type).

Módulo puro: retrocompatible (sin work_item_type = comportamiento previo) y
source=="matrix" SOLO cuando el operador configuró el cell.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from harness.task_states import resolve_task_state_plan  # noqa: E402


def _profile(machine: dict) -> dict:
    return {"tracker_state_machine": {"developer": machine}}


_LEGACY = {"in_progress": "In Progress", "next_state_ok": "Code Review"}


def test_sin_by_work_item_type_no_es_matrix():
    plan = resolve_task_state_plan(_profile(_LEGACY), "developer", "Task")
    assert plan.source == "config"
    assert (plan.in_progress, plan.final_ok) == ("In Progress", "Code Review")


def test_work_item_type_none_identico_a_hoy():
    plan = resolve_task_state_plan(
        _profile({**_LEGACY, "by_work_item_type": {"Task": {"next_state_ok": "Ready for QA"}}}),
        "developer",
        None,
    )
    assert plan.source == "config"
    assert plan.final_ok == "Code Review", "sin work_item_type NO debe mirar la matriz"


def test_match_case_insensitive():
    plan = resolve_task_state_plan(
        _profile({**_LEGACY, "by_work_item_type": {"Task": {"in_progress": "Active",
                                                            "next_state_ok": "Ready for QA"}}}),
        "developer",
        "task",
    )
    assert plan.source == "matrix"
    assert (plan.in_progress, plan.final_ok) == ("Active", "Ready for QA")


def test_tipo_desconocido_cae_a_agent_level():
    plan = resolve_task_state_plan(
        _profile({**_LEGACY, "by_work_item_type": {"Task": {"next_state_ok": "Ready for QA"}}}),
        "developer",
        "Feature",
    )
    assert plan.source == "config"
    assert plan.final_ok == "Code Review"


def test_cell_vacio_cae_a_agent_level():
    plan = resolve_task_state_plan(
        _profile({**_LEGACY, "by_work_item_type": {"Task": {}}}),
        "developer",
        "Task",
    )
    assert plan.source == "config"
    assert plan.final_ok == "Code Review"


def test_cell_solo_in_progress():
    plan = resolve_task_state_plan(
        _profile({**_LEGACY, "by_work_item_type": {"Epic": {"in_progress": "Active"}}}),
        "developer",
        "Epic",
    )
    assert plan.source == "matrix"
    assert plan.in_progress == "Active"
    assert plan.final_ok is None, "el cell manda: sin next_state_ok en el cell, no hay final"


def test_agent_type_none():
    plan = resolve_task_state_plan(_profile(_LEGACY), None, "Task")
    assert plan.source == "no_agent_type"
    assert (plan.in_progress, plan.final_ok) == (None, None)


@pytest.mark.parametrize(
    "profile, wit",
    [
        ("no soy un dict", "Task"),
        ({"tracker_state_machine": {"developer": "no soy un dict"}}, "Task"),
        ({"tracker_state_machine": {"developer": {"by_work_item_type": ["lista", "mal"]}}}, "Task"),
        ({"tracker_state_machine": {"developer": {"by_work_item_type": {"Task": "no dict"}}}}, "Task"),
        ({}, "   "),
    ],
)
def test_defensivo_no_lanza(profile, wit):
    plan = resolve_task_state_plan(profile, "developer", wit)
    assert plan.source in {"absent", "config", "no_agent_type"}
    assert plan.source != "matrix"


@pytest.mark.parametrize(
    "machine, expected",
    [
        (_LEGACY, ("In Progress", "Code Review", "config")),
        ({"in_progress": "  ", "next_state_ok": "Done"}, (None, "Done", "config")),
        ({}, (None, None, "absent")),
    ],
)
def test_backcompat_sin_work_item_type_identico(machine, expected):
    """Sin work_item_type, el resultado es idéntico al comportamiento previo."""
    legacy = resolve_task_state_plan(_profile(machine), "developer")
    nuevo = resolve_task_state_plan(_profile(machine), "developer", None)
    assert (legacy.in_progress, legacy.final_ok, legacy.source) == expected
    assert (nuevo.in_progress, nuevo.final_ok, nuevo.source) == expected


def test_applicable_states_cubre_el_estado_de_la_matriz():
    from harness.task_states import applicable_states

    plan = resolve_task_state_plan(
        _profile({**_LEGACY, "by_work_item_type": {"Bug": {"next_state_ok": "Ready for QA"}}}),
        "developer",
        "Bug",
    )
    assert plan.source == "matrix"
    assert applicable_states(plan) == frozenset({"Ready for QA"})
    assert "Code Review" not in applicable_states(plan), (
        "el centinela NO debe permitir el estado agent-level cuando manda la matriz"
    )
