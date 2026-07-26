"""Plan 201 F1 — Scanner determinista de soluciones .sln.

Read-only, acotado y sin LLM: el mismo árbol siempre da el mismo catálogo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import solution_scanner as sc  # noqa: E402

_SLN = """Microsoft Visual Studio Solution File, Format Version 12.00
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Web.App", "Web.App\\Web.App.csproj", "{11111111-1111-1111-1111-111111111111}"
EndProject
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Tool.Cli", "Tool.Cli\\Tool.Cli.csproj", "{22222222-2222-2222-2222-222222222222}"
EndProject
Global
EndGlobal
"""

_CSPROJ_WEB = ('<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup>'
               "<TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>")
_CSPROJ_CLI = ('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
               "<TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>")


def _mk_solution(root: Path, name: str = "MiSolucion") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.sln").write_text(_SLN, encoding="utf-8")
    (root / "Web.App").mkdir(exist_ok=True)
    (root / "Web.App" / "Web.App.csproj").write_text(_CSPROJ_WEB, encoding="utf-8")
    (root / "Tool.Cli").mkdir(exist_ok=True)
    (root / "Tool.Cli" / "Tool.Cli.csproj").write_text(_CSPROJ_CLI, encoding="utf-8")
    return root / f"{name}.sln"


def test_scan_none_and_missing_returns_empty(tmp_path):
    assert sc.scan_solutions(None) == []
    assert sc.scan_solutions("") == []
    assert sc.scan_solutions(str(tmp_path / "no-existe")) == []
    assert sc.scan_solutions_ex(None) == {"solutions": [], "truncated": False}


def test_scan_no_sln_returns_empty(tmp_path):
    (tmp_path / "readme.md").write_text("hola", encoding="utf-8")
    (tmp_path / "code.py").write_text("x = 1", encoding="utf-8")

    assert sc.scan_solutions(str(tmp_path)) == []


def test_scan_finds_sln_and_parses_projects(tmp_path):
    _mk_solution(tmp_path / "src")

    sols = sc.scan_solutions(str(tmp_path))

    assert len(sols) == 1
    sol = sols[0]
    assert sol["slug"] == "misolucion"
    assert sol["sln_name"] == "MiSolucion"
    assert sol["friendly_name"] == "Mi Solucion"
    tipos = {p["name"]: p["type"] for p in sol["projects"]}
    assert tipos == {"Web.App": "web", "Tool.Cli": "console"}
    assert all(p["target_framework"] == "net8.0" for p in sol["projects"])
    assert all(os.path.isabs(p["csproj_path"]) for p in sol["projects"])


def test_infer_types(tmp_path):
    def _csproj(rel: str, body: str) -> str:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return str(path)

    assert sc._infer_project(_csproj("a/a.csproj", _CSPROJ_WEB)) == ("web", "net8.0")
    assert sc._infer_project(_csproj("b/b.csproj", _CSPROJ_CLI)) == ("console", "net8.0")
    assert sc._infer_project(
        _csproj("c/c.csproj", '<Project Sdk="Microsoft.NET.Sdk.Worker"></Project>')
    ) == ("service", "")
    assert sc._infer_project(
        _csproj("d/d.csproj", '<Project Sdk="Microsoft.NET.Sdk"></Project>')
    ) == ("library", "")

    # web por web.config (proyecto clásico sin SDK web)
    clasico = _csproj("e/e.csproj", "<Project></Project>")
    (tmp_path / "e" / "web.config").write_text("<configuration/>", encoding="utf-8")
    assert sc._infer_project(clasico)[0] == "web"

    assert sc._infer_project(str(tmp_path / "no-existe.csproj")) == ("unknown", "")


def test_slugify_matches_app_id_regex():
    from services.deploy_planner import _APP_ID_RE

    for nombre in ["Mi Solución", "  ESPACIOS  ", "raro!!!@#$", "Ünïcode", "123start",
                   "x" * 120, "___", "MiSolucion.Core"]:
        slug = sc.slugify_solution(nombre)
        assert _APP_ID_RE.match(slug), f"{nombre!r} -> {slug!r} no matchea el regex de app id"


def test_duplicate_names_get_unique_slugs(tmp_path):
    _mk_solution(tmp_path / "a")
    _mk_solution(tmp_path / "b")
    _mk_solution(tmp_path / "c")

    slugs = [s["slug"] for s in sc.scan_solutions(str(tmp_path))]

    assert len(slugs) == 3
    assert len(set(slugs)) == 3, f"slugs duplicados: {slugs}"
    assert slugs == ["misolucion", "misolucion-2", "misolucion-3"]


def test_ignores_bin_obj_and_depth_cap(tmp_path):
    _mk_solution(tmp_path / "bin", name="Oculta")
    _mk_solution(tmp_path / "obj" / "sub", name="Oculta2")
    profundo = tmp_path
    for i in range(10):
        profundo = profundo / f"n{i}"
    _mk_solution(profundo, name="Profunda")
    _mk_solution(tmp_path / "src", name="Visible")

    nombres = {s["sln_name"] for s in sc.scan_solutions(str(tmp_path))}

    assert "Visible" in nombres
    assert "Oculta" not in nombres and "Oculta2" not in nombres, "bin/obj deben ignorarse"
    assert "Profunda" not in nombres, "más allá de _MAX_DEPTH no se recorre"


def test_corrupt_sln_no_crash(tmp_path):
    (tmp_path / "Rota.sln").write_text("basura \x00 sin estructura", encoding="utf-8")

    sols = sc.scan_solutions(str(tmp_path))

    assert len(sols) == 1
    assert sols[0]["projects"] == []


def test_csproj_referenciado_inexistente(tmp_path):
    (tmp_path / "Fantasma.sln").write_text(_SLN, encoding="utf-8")

    sol = sc.scan_solutions(str(tmp_path))[0]

    assert len(sol["projects"]) == 2
    assert all(p["type"] == "unknown" and p["target_framework"] == "" for p in sol["projects"])


def test_title_case_splits_camelcase():
    assert sc._title_case("MiSolucion") == "Mi Solucion"
    assert sc._title_case("core_api.web") == "Core Api Web"
    assert sc._title_case("") == ""


def test_truncation_flag_via_scan_ex(tmp_path, monkeypatch):
    _mk_solution(tmp_path / "src")
    monkeypatch.setattr(sc, "_MAX_ENTRIES", 1, raising=True)

    assert sc.scan_solutions_ex(str(tmp_path))["truncated"] is True


def test_scanner_no_importa_llm_ni_red():
    fuente = (ROOT / "services" / "solution_scanner.py").read_text(encoding="utf-8")
    lineas_import = [ln for ln in fuente.splitlines() if ln.startswith(("import ", "from "))]

    for prohibido in ("requests", "urllib", "llm", "copilot", "runtime"):
        assert not any(prohibido in ln for ln in lineas_import), \
            f"el scanner no debe importar {prohibido}"


def test_orden_determinista(tmp_path):
    _mk_solution(tmp_path / "z", name="Zeta")
    _mk_solution(tmp_path / "a", name="Alfa")

    primera = [s["sln_path"] for s in sc.scan_solutions(str(tmp_path))]
    segunda = [s["sln_path"] for s in sc.scan_solutions(str(tmp_path))]

    assert primera == segunda == sorted(primera)
