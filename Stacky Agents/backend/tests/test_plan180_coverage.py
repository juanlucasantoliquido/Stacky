"""Plan 180 F3 — Cobertura del diff: match_diff_items (pura, sin disco).

Ver Stacky Agents/docs/180_PLAN_PUENTE_DIFF_REPO_...md §F3 (KPI-5).
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.dbcompare_repo_scripts import match_diff_items


def _script(path, tables=None, qualified=None, ticket=None, mtime=0):
    return {
        "path": path, "ticket": ticket, "tables": tables or [],
        "tables_qualified": qualified or [], "mtime": mtime,
    }


def _item(name, object_type="table", schema="dbo", action="added", severity="warn"):
    return {"object_type": object_type, "schema": schema, "name": name,
            "action": action, "severity": severity}


def test_cobertura_2_de_3():
    diff = {"items": [_item("RIDIOMA"), _item("RTABL"), _item("RNUEVA")]}
    index = {"scripts": [
        _script("a.sql", tables=["RIDIOMA"]),
        _script("b.sql", tables=["RTABL"]),
    ]}
    out = match_diff_items(diff, index)
    assert out["covered_count"] == 2
    assert out["total_count"] == 3
    rnueva = next(i for i in out["items"] if i["name"] == "RNUEVA")
    assert rnueva["candidates"] == []


def test_match_calificado():
    diff = {"items": [_item("RIDIOMA", schema="dbo")]}
    index = {"scripts": [_script("a.sql", qualified=["DBO.RIDIOMA"])]}
    out = match_diff_items(diff, index)
    cands = out["items"][0]["candidates"]
    assert len(cands) == 1
    assert cands[0]["matched_by"] == "SCHEMA.TABLE"


def test_matched_by_name_pelado():
    diff = {"items": [_item("RIDIOMA", schema="ventas")]}
    index = {"scripts": [_script("a.sql", tables=["RIDIOMA"])]}
    out = match_diff_items(diff, index)
    cands = out["items"][0]["candidates"]
    assert len(cands) == 1
    assert cands[0]["matched_by"] == "TABLE"


def test_ranking_calificado_primero():
    diff = {"items": [_item("RIDIOMA", schema="dbo")]}
    index = {"scripts": [
        _script("por_nombre.sql", tables=["RIDIOMA"], mtime=9999),          # nuevo, débil
        _script("calificado.sql", qualified=["DBO.RIDIOMA"], mtime=1),      # viejo, fuerte
    ]}
    out = match_diff_items(diff, index)
    cands = out["items"][0]["candidates"]
    assert cands[0]["path"] == "calificado.sql"
    assert cands[0]["matched_by"] == "SCHEMA.TABLE"
    assert cands[1]["path"] == "por_nombre.sql"


def test_view_matchea_como_tabla():
    diff = {"items": [_item("VCLIENTES", object_type="view")]}
    index = {"scripts": [_script("v.sql", tables=["VCLIENTES"])]}
    out = match_diff_items(diff, index)
    assert out["covered_count"] == 1
    assert len(out["items"][0]["candidates"]) == 1


def test_sequence_sin_candidatos():
    diff = {"items": [_item("SEQ1", object_type="sequence")]}
    index = {"scripts": [_script("s.sql", tables=["SEQ1"])]}
    out = match_diff_items(diff, index)
    assert out["items"][0]["candidates"] == []
    assert out["covered_count"] == 0


def test_case_insensitive():
    diff = {"items": [_item("ridioma")]}
    index = {"scripts": [_script("a.sql", tables=["RIDIOMA"])]}
    out = match_diff_items(diff, index)
    assert len(out["items"][0]["candidates"]) == 1


def test_cap_10_candidatos():
    diff = {"items": [_item("RIDIOMA")]}
    index = {"scripts": [_script(f"s{i:02d}.sql", tables=["RIDIOMA"], mtime=i) for i in range(12)]}
    out = match_diff_items(diff, index)
    assert len(out["items"][0]["candidates"]) == 10
