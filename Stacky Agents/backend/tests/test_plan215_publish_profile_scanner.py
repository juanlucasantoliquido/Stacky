"""Plan 215 F1 — scanner de perfiles de publish + plan determinista (PURO)."""
from __future__ import annotations

import os

from services import publish_profile_scanner as pps

_SDK_CSPROJ = '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup/>\n</Project>\n'
_CLASSIC_CSPROJ = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<Project ToolsVersion="15.0" DefaultTargets="Build" '
    'xmlns="http://schemas.microsoft.com/developer/msbuild/2003">\n</Project>\n'
)

_TC_FULL = {"available": True, "builder": "dotnet",
            "dotnet_path": "dotnet", "msbuild_path": "msbuild"}


def _mk_project(tmp_path, name, content, profiles=None, ptype="web"):
    pdir = tmp_path / name
    pdir.mkdir(parents=True, exist_ok=True)
    csproj = pdir / f"{name}.csproj"
    csproj.write_text(content, encoding="utf-8")
    for prof_name, body in (profiles or {}).items():
        prof_dir = pdir / "Properties" / "PublishProfiles"
        prof_dir.mkdir(parents=True, exist_ok=True)
        (prof_dir / f"{prof_name}.pubxml").write_text(body, encoding="utf-8")
    return {"name": name, "csproj_path": str(csproj), "type": ptype,
            "target_framework": "net8.0"}


def _pubxml(method="FileSystem", url="C:\\out"):
    return (
        '<Project><PropertyGroup>'
        f'<WebPublishMethod>{method}</WebPublishMethod>'
        f'<publishUrl>{url}</publishUrl>'
        '</PropertyGroup></Project>'
    )


def test_scan_profiles_finds_pubxml_and_method(tmp_path):
    p = _mk_project(tmp_path, "Web", _SDK_CSPROJ, {"Prod": _pubxml()})
    out = pps.scan_publish_profiles([p])
    entries = out[p["csproj_path"]]
    assert len(entries) == 1
    assert entries[0]["name"] == "Prod"
    assert entries[0]["method"] == "FileSystem"
    assert entries[0]["publish_url"] == "C:\\out"


def test_scan_profiles_missing_dir_returns_empty(tmp_path):
    p = _mk_project(tmp_path, "NoProf", _SDK_CSPROJ)
    assert pps.scan_publish_profiles([p]) == {}


def test_scan_profiles_method_case_insensitive(tmp_path):
    p = _mk_project(tmp_path, "W2", _SDK_CSPROJ, {"P": _pubxml(method="fileSystem")})
    assert pps.scan_publish_profiles([p])[p["csproj_path"]][0]["method"] == "FileSystem"


def test_detect_sdk_style_true_and_false(tmp_path):
    sdk = _mk_project(tmp_path, "A", _SDK_CSPROJ)
    classic = _mk_project(tmp_path, "B", _CLASSIC_CSPROJ)
    assert pps.detect_sdk_style(sdk["csproj_path"]) is True
    assert pps.detect_sdk_style(classic["csproj_path"]) is False
    assert pps.detect_sdk_style(str(tmp_path / "no-existe.csproj")) is False


def test_resolve_auto_sdk_web_is_dotnet_publish(tmp_path):
    p = _mk_project(tmp_path, "Web", _SDK_CSPROJ)
    sol = {"sln_path": str(tmp_path / "S.sln"), "projects": [p]}
    plan = pps.resolve_publish_plan(sol, {"mode": "auto", "configuration": "Release"}, _TC_FULL)
    assert plan["mode_effective"] == "dotnet_publish"
    assert plan["supported"] is True
    assert plan["argv_tail"] == ["publish", p["csproj_path"], "-c", "Release", "--nologo"]


def test_resolve_auto_classic_with_filesystem_pubxml_is_msbuild_pubxml(tmp_path):
    p = _mk_project(tmp_path, "Legacy", _CLASSIC_CSPROJ, {"Prod": _pubxml()})
    sol = {"sln_path": str(tmp_path / "S.sln"), "projects": [p]}
    plan = pps.resolve_publish_plan(sol, {"mode": "auto", "configuration": "Release"}, _TC_FULL)
    assert plan["mode_effective"] == "msbuild_pubxml"
    assert plan["supported"] is True
    assert "/p:DeployOnBuild=true" in plan["argv_tail"]
    assert "/p:PublishProfile=Prod" in plan["argv_tail"]


def test_resolve_auto_no_target_project_is_build_only(tmp_path):
    sol = {"sln_path": str(tmp_path / "S.sln"), "projects": []}
    plan = pps.resolve_publish_plan(sol, {"mode": "auto"}, _TC_FULL)
    assert plan["mode_effective"] == "build_only"
    assert plan["supported"] is True
    assert plan["target"] == sol["sln_path"]


def test_resolve_msdeploy_pubxml_unsupported(tmp_path):
    p = _mk_project(tmp_path, "Legacy", _CLASSIC_CSPROJ, {"Rem": _pubxml(method="MSDeploy")})
    sol = {"sln_path": str(tmp_path / "S.sln"), "projects": [p]}
    plan = pps.resolve_publish_plan(
        sol, {"mode": "msbuild_pubxml", "publish_profile": "Rem"}, _TC_FULL
    )
    assert plan["supported"] is False
    assert plan["reason"] == "pubxml_remoto_no_soportado"


def test_resolve_configured_pubxml_missing_reports_reason(tmp_path):
    p = _mk_project(tmp_path, "Legacy", _CLASSIC_CSPROJ, {"Prod": _pubxml()})
    sol = {"sln_path": str(tmp_path / "S.sln"), "projects": [p]}
    plan = pps.resolve_publish_plan(sol, {"mode": "auto", "publish_profile": "Fantasma"}, _TC_FULL)
    assert plan["supported"] is False
    assert plan["reason"] == "pubxml_no_encontrado"


def test_resolve_dotnet_missing_dotnet_path_unsupported_even_if_builder_dotnet(tmp_path):
    # C5 — la condicion es SOLO dotnet_path, no builder.
    p = _mk_project(tmp_path, "Web", _SDK_CSPROJ)
    sol = {"sln_path": str(tmp_path / "S.sln"), "projects": [p]}
    tc = {"available": True, "builder": "dotnet", "dotnet_path": None, "msbuild_path": "msbuild"}
    plan = pps.resolve_publish_plan(sol, {"mode": "auto"}, tc)
    assert plan["supported"] is False
    assert plan["reason"] == "requiere_dotnet_sdk"


def test_resolve_never_raises_on_bad_paths():
    plan = pps.resolve_publish_plan(
        {"sln_path": "", "projects": [{"csproj_path": "\x00bad", "type": "web"}]},
        {"mode": "auto"}, {"available": False},
    )
    assert plan["mode_effective"] in ("build_only", "dotnet_publish", "msbuild_pubxml")
    assert pps.scan_publish_profiles(None) == {}
    assert pps.scan_publish_profiles([{}]) == {}


def test_module_is_deterministic_no_llm_no_shell():
    src = open(pps.__file__, encoding="utf-8").read()
    for forbidden in ("shell=True", "import requests", "copilot"):
        assert forbidden not in src, f"{forbidden} no debe existir en un modulo determinista"
    assert os.path.basename(pps.__file__) == "publish_profile_scanner.py"
