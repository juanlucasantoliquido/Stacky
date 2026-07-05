"""tests/test_plan89_environment_layout.py — F1: build_environment_layout /
layout_fingerprint PUROS (sin I/O). Fixture de catálogo reusada de
tests/fixtures/plan88_resolution_cases.json (SOLO lectura, jamás modificado).
"""
import copy
import json
from pathlib import Path

from services.environment_init import build_environment_layout, layout_fingerprint

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "plan88_resolution_cases.json")
    .read_text(encoding="utf-8")
)
_CATALOG = _FIXTURE["catalog"]  # Mul2Bane(entry) IncHost/RSCore(processing) RsExtrae/SinGrupo(output) AgendaX(processing)

_SETTINGS = {
    "environment_root": "C:\\ambientes\\pacifico",
    "folder_layout": {
        "entry": ["IN_"],
        "processing": ["productivas"],
        "output": ["salida"],
        "default": [],
    },
    "per_process_subfolder": False,
}


def test_f1_pacifico_layout_basic():
    result = build_environment_layout(_CATALOG, _SETTINGS)
    assert result == ["IN_", "productivas", "salida"]


def test_f1_per_process_subfolders():
    settings = copy.deepcopy(_SETTINGS)
    settings["per_process_subfolder"] = True
    result = build_environment_layout(_CATALOG, settings)
    for expected in ("IN_/mul2bane", "productivas/inchost", "productivas/rscore", "salida/rsextrae"):
        assert expected in result
    for base in ("IN_", "productivas", "salida"):
        assert base in result


def test_f1_unknown_kind_uses_default():
    catalog = [{"name": "X", "kind": "zzz"}]
    settings = copy.deepcopy(_SETTINGS)
    settings["folder_layout"]["default"] = ["misc"]
    result = build_environment_layout(catalog, settings)
    assert "misc" in result


def test_f1_empty_settings_empty():
    assert build_environment_layout(_CATALOG, None) == []
    settings_no_layout = {"environment_root": "C:\\x"}
    assert build_environment_layout(_CATALOG, settings_no_layout) == []


def test_f1_unsafe_segments_omitted():
    settings = copy.deepcopy(_SETTINGS)
    settings["folder_layout"] = {"entry": ["../fuga", "C:\\abs", "ok"]}
    result = build_environment_layout(_CATALOG, settings)
    assert result == ["ok"]


def test_f1_traversal_process_name_sanitized():
    catalog = [{"name": "../../evil", "kind": "entry"}]
    settings = copy.deepcopy(_SETTINGS)
    settings["per_process_subfolder"] = True
    result = build_environment_layout(catalog, settings)
    assert "IN_/evil" in result
    for p in result:
        assert ".." not in p
        for comp in p.split("/"):
            assert comp != ".."


def test_f1_non_dict_entries_ignored():
    catalog = ["basura", 42, {"name": "Mul2Bane", "kind": "entry"}]
    result = build_environment_layout(catalog, _SETTINGS)
    assert result == ["IN_"]


def test_f1_windows_invalid_chars_omitted():
    settings = copy.deepcopy(_SETTINGS)
    settings["folder_layout"] = {"entry": ["IN|X", "ok"]}
    assert build_environment_layout(_CATALOG, settings) == ["ok"]

    settings2 = copy.deepcopy(_SETTINGS)
    settings2["folder_layout"] = {"entry": ["aux", "ok"]}
    assert build_environment_layout(_CATALOG, settings2) == ["ok"]

    settings3 = copy.deepcopy(_SETTINGS)
    settings3["folder_layout"] = {"entry": ["carpeta.", "ok"]}
    assert build_environment_layout(_CATALOG, settings3) == ["ok"]


def test_f1_reserved_names_omitted():
    settings = copy.deepcopy(_SETTINGS)
    settings["folder_layout"] = {"entry": ["CON", "lpt1", "normal"]}
    result = build_environment_layout(_CATALOG, settings)
    assert result == ["normal"]

    catalog = [{"name": "CON", "kind": "entry"}]
    settings2 = copy.deepcopy(_SETTINGS)
    settings2["folder_layout"] = {"entry": ["base"]}
    settings2["per_process_subfolder"] = True
    result2 = build_environment_layout(catalog, settings2)
    assert "base/p-con" in result2
    assert "base/con" not in result2


def test_f1_case_insensitive_dedup():
    settings = copy.deepcopy(_SETTINGS)
    settings["folder_layout"] = {"entry": ["IN_"], "output": ["in_"]}
    result = build_environment_layout(_CATALOG, settings)
    assert len(result) == 1


def test_f1_deterministic_and_pure():
    catalog_copy = copy.deepcopy(_CATALOG)
    settings_copy = copy.deepcopy(_SETTINGS)
    r1 = build_environment_layout(catalog_copy, settings_copy)
    r2 = build_environment_layout(catalog_copy, settings_copy)
    assert r1 == r2
    assert catalog_copy == _CATALOG
    assert settings_copy == _SETTINGS

    fp1 = layout_fingerprint("C:\\ambientes\\pacifico", r1)
    fp2 = layout_fingerprint("C:\\ambientes\\pacifico", r1)
    assert fp1 == fp2
    fp_diff_root = layout_fingerprint("C:\\otro", r1)
    assert fp_diff_root != fp1
    fp_diff_paths = layout_fingerprint("C:\\ambientes\\pacifico", r1 + ["extra"])
    assert fp_diff_paths != fp1
