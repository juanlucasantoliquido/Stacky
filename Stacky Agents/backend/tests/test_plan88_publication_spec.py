"""Tests F1 — Plan 88: services/publication_spec.py (modulo PURO).

Fixture compartido py<->ts: tests/fixtures/plan88_resolution_cases.json.
"""
import copy
import json
from pathlib import Path

import pytest

from services.publication_spec import build_publication_spec, resolve_processes
from services.pipeline_spec import dict_to_spec
from services.pipeline_renderers import to_ado_yaml, to_gitlab_yaml

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "plan88_resolution_cases.json")
    .read_text(encoding="utf-8")
)
_CATALOG = _FIXTURE["catalog"]


def _names(entries):
    return [e["name"] for e in entries]


def test_f1_todo_includes_everything():
    preset = {"name": "t", "mode": "todo", "groups": []}
    resolved, unknown = resolve_processes(preset, _CATALOG)
    assert _names(resolved) == ["Mul2Bane", "IncHost", "RSCore", "RsExtrae", "AgendaX", "SinGrupo"]
    assert unknown == []
    result = build_publication_spec(preset, _CATALOG)
    stage_names = [s["name"] for s in result["spec"]["stages"]]
    assert stage_names == ["entry", "processing", "output"]


def test_f1_todo_is_dynamic():
    preset = {"name": "t", "mode": "todo", "groups": []}
    resolved_before, _ = resolve_processes(preset, _CATALOG)
    catalog_plus = _CATALOG + [{"name": "Extra", "kind": "output", "publish_group": "batch"}]
    resolved_after, _ = resolve_processes(preset, catalog_plus)
    assert len(resolved_after) == len(resolved_before) + 1
    assert "Extra" in _names(resolved_after)


def test_f1_todo_empty_catalog():
    preset = {"name": "t", "mode": "todo", "groups": []}
    result = build_publication_spec(preset, [])
    assert result["resolved"] == []
    assert result["unknown_processes"] == []
    spec = dict_to_spec(result["spec"])
    assert spec.validate() != []


def test_f1_groups_filter_batch():
    preset = {"name": "t", "mode": "todo", "groups": ["batch"]}
    resolved, unknown = resolve_processes(preset, _CATALOG)
    assert _names(resolved) == ["Mul2Bane", "IncHost", "RSCore", "RsExtrae"]
    assert unknown == []


def test_f1_groups_filter_agenda():
    preset = {"name": "t", "mode": "todo", "groups": ["agenda"]}
    resolved, unknown = resolve_processes(preset, _CATALOG)
    assert _names(resolved) == ["AgendaX"]


def test_f1_groups_key_absent_no_filter():
    preset = {"name": "t", "mode": "todo"}
    resolved, _ = resolve_processes(preset, _CATALOG)
    assert len(resolved) == 6


def test_f1_selection_by_name_with_unknown():
    preset = {"name": "t", "mode": "selection", "process_names": ["RSCore", "NoExiste", "Mul2Bane"], "groups": []}
    resolved, unknown = resolve_processes(preset, _CATALOG)
    assert _names(resolved) == ["Mul2Bane", "RSCore"]
    assert unknown == ["NoExiste"]


def test_f1_stage_order_canonical():
    preset = {"name": "t", "mode": "todo", "groups": []}
    result = build_publication_spec(preset, _CATALOG)
    stages = result["spec"]["stages"]
    assert [s["name"] for s in stages] == ["entry", "processing", "output"]
    entry_stage = stages[0]
    assert any("mul2bane" in j["name"] for j in entry_stage["jobs"])
    output_stage = stages[-1]
    assert any("rsextrae" in j["name"] for j in output_stage["jobs"])


def test_f1_unknown_kind_goes_otros():
    catalog = _CATALOG + [{"name": "Zeta", "kind": "zzz", "publish_group": "batch"}]
    preset = {"name": "t", "mode": "todo", "groups": []}
    result = build_publication_spec(preset, catalog)
    stages = result["spec"]["stages"]
    assert stages[-1]["name"] == "otros"
    assert any("zeta" in j["name"] for j in stages[-1]["jobs"])


def test_f1_non_dict_entries_ignored():
    catalog = ["basura", 42, {"name": "Valida", "kind": "entry", "publish_group": "batch"}]
    preset = {"name": "t", "mode": "todo", "groups": []}
    resolved, unknown = resolve_processes(preset, catalog)
    assert _names(resolved) == ["Valida"]
    assert unknown == []


def test_f1_template_per_kind_and_placeholder():
    settings = {"step_templates": {"entry": "deploy-entry {process_name} --now"}}
    preset = {"name": "t", "mode": "todo", "groups": []}
    result = build_publication_spec(preset, _CATALOG, settings)
    entry_stage = result["spec"]["stages"][0]
    mul2bane_job = next(j for j in entry_stage["jobs"] if "mul2bane" in j["name"])
    assert mul2bane_job["steps"][0]["script"] == "deploy-entry Mul2Bane --now"
    processing_stage = result["spec"]["stages"][1]
    rscore_job = next(j for j in processing_stage["jobs"] if "rscore" in j["name"])
    assert rscore_job["steps"][0]["script"] == 'echo "[stacky] publicar RSCore"'


def test_f1_braces_in_template_safe():
    settings = {"step_templates": {"entry": "run {process_name} ${VAR} {otra}"}}
    preset = {"name": "t", "mode": "todo", "groups": []}
    result = build_publication_spec(preset, _CATALOG, settings)
    entry_stage = result["spec"]["stages"][0]
    mul2bane_job = next(j for j in entry_stage["jobs"] if "mul2bane" in j["name"])
    assert mul2bane_job["steps"][0]["script"] == "run Mul2Bane ${VAR} {otra}"


def test_f1_spec_renders_via_plan73():
    preset = {"name": "t", "mode": "todo", "groups": []}
    result = build_publication_spec(preset, _CATALOG)
    spec = dict_to_spec(result["spec"])
    assert spec.validate() == []
    to_ado_yaml(spec)
    to_gitlab_yaml(spec)


def test_f1_pure_no_mutation():
    preset = {"name": "t", "mode": "todo", "groups": []}
    preset_copy = copy.deepcopy(preset)
    catalog_copy = copy.deepcopy(_CATALOG)
    build_publication_spec(preset, _CATALOG)
    assert preset == preset_copy
    assert _CATALOG == catalog_copy


@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=[c["id"] for c in _FIXTURE["cases"]])
def test_f1_shared_fixture_cases(case):
    resolved, unknown = resolve_processes(case["preset"], _FIXTURE["catalog"])
    assert [e["name"] for e in resolved] == case["resolved"]
    assert unknown == case["unknown"]
