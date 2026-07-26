"""Plan 211 F1 — Inspector post-build.

Lo que bloquea es escribir FUERA del proyecto (ruta absoluta) o mencionar a otro
cliente; un evento relativo solo avisa.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.post_build_inspector import findings_to_dicts, inspect_projects  # noqa: E402

_FOREIGN = {"ripley": {"source_project": "ripley", "kind": "workspace"}}


def _csproj(tmp_path: Path, body: str, name: str = "App.csproj") -> str:
    p = tmp_path / name
    p.write_text(f"<Project Sdk='Microsoft.NET.Sdk'>{body}</Project>", encoding="utf-8")
    return str(p)


def test_empty_returns_empty(tmp_path):
    assert inspect_projects([], workspace_root=str(tmp_path)) == []
    assert inspect_projects([str(tmp_path / "no-existe.csproj")],
                            workspace_root=str(tmp_path)) == []


def test_csproj_sin_eventos_no_reporta(tmp_path):
    ruta = _csproj(tmp_path, "<PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>")

    assert inspect_projects([ruta], workspace_root=str(tmp_path)) == []


def test_post_build_absolute_is_blocking(tmp_path):
    ruta = _csproj(tmp_path, r'<PostBuildEvent>xcopy "$(TargetDir)*" "C:\Deploy\bin"</PostBuildEvent>')

    findings = inspect_projects([ruta], workspace_root=str(tmp_path))

    assert len(findings) == 1
    assert findings[0].kind == "post_build_event"
    assert findings[0].severity == "blocking"
    assert "ruta absoluta" in findings[0].detail


def test_post_build_relative_is_warning(tmp_path):
    ruta = _csproj(tmp_path, "<PostBuildEvent>copy $(TargetPath) ..\\shared</PostBuildEvent>")

    findings = inspect_projects([ruta], workspace_root=str(tmp_path))

    assert findings[0].severity == "warning"


def test_post_build_con_token_ajeno_es_blocking(tmp_path):
    ruta = _csproj(tmp_path, "<PostBuildEvent>copy $(TargetPath) ..\\ripley\\bin</PostBuildEvent>")

    findings = inspect_projects([ruta], workspace_root=str(tmp_path), foreign_tokens=_FOREIGN)

    assert findings[0].severity == "blocking"
    assert "ripley" in findings[0].detail


def test_copy_task_absolute_is_blocking(tmp_path):
    ruta = _csproj(tmp_path, r'<Target Name="X"><Copy SourceFiles="a" DestinationFolder="C:\otro\bin" /></Target>')

    findings = [f for f in inspect_projects([ruta], workspace_root=str(tmp_path))
                if f.kind == "copy_task"]

    assert findings and findings[0].severity == "blocking"


def test_copy_task_relative_is_warning(tmp_path):
    ruta = _csproj(tmp_path, '<Target Name="X"><Copy SourceFiles="a" DestinationFolder="bin\\out" /></Target>')

    findings = [f for f in inspect_projects([ruta], workspace_root=str(tmp_path))
                if f.kind == "copy_task"]

    assert findings and findings[0].severity == "warning"


def test_after_targets_with_foreign_token_blocking(tmp_path):
    ruta = _csproj(
        tmp_path,
        '<Target Name="Post" AfterTargets="Build"><Exec Command="deploy ripley" /></Target>',
    )

    findings = [f for f in inspect_projects([ruta], workspace_root=str(tmp_path),
                                            foreign_tokens=_FOREIGN)
                if f.kind == "after_targets"]

    assert findings and findings[0].severity == "blocking"


def test_after_targets_relativo_es_warning(tmp_path):
    ruta = _csproj(
        tmp_path,
        '<Target Name="Post" AfterTargets="Build"><Exec Command="echo hola" /></Target>',
    )

    findings = [f for f in inspect_projects([ruta], workspace_root=str(tmp_path))
                if f.kind == "after_targets"]

    assert findings and findings[0].severity == "warning"


def test_output_path_foreign_token_blocking_vs_own_absolute_warning(tmp_path):
    ajeno = _csproj(tmp_path, r"<PropertyGroup><OutputPath>C:\ripley\bin</OutputPath></PropertyGroup>",
                    name="Ajeno.csproj")
    propio = _csproj(tmp_path, r"<PropertyGroup><OutputPath>C:\propio\bin</OutputPath></PropertyGroup>",
                     name="Propio.csproj")

    f_ajeno = inspect_projects([ajeno], workspace_root=str(tmp_path), foreign_tokens=_FOREIGN)[0]
    f_propio = inspect_projects([propio], workspace_root=str(tmp_path), foreign_tokens=_FOREIGN)[0]

    assert f_ajeno.kind == "foreign_output_path" and f_ajeno.severity == "blocking"
    assert f_propio.kind == "abs_output_path" and f_propio.severity == "warning", \
        "una ruta absoluta propia es común y benigna: avisa, no bloquea"


def test_token_ajeno_por_limite_de_palabra(tmp_path):
    """'crea' no puede matchear dentro de 'CrearCliente'."""
    corto = {"crea": {"source_project": "crea", "kind": "workspace"}}
    ruta = _csproj(tmp_path, "<PostBuildEvent>call CrearCliente.bat</PostBuildEvent>")

    findings = inspect_projects([ruta], workspace_root=str(tmp_path), foreign_tokens=corto)

    assert findings[0].severity == "warning", "substring NO puede bloquear"


def test_unreadable_file_skipped_no_crash(tmp_path):
    assert inspect_projects([str(tmp_path)], workspace_root=str(tmp_path)) == []
    assert inspect_projects([None, ""], workspace_root=str(tmp_path)) == []


def test_findings_to_dicts_shape(tmp_path):
    ruta = _csproj(tmp_path, r'<PostBuildEvent>xcopy "C:\x" "C:\y"</PostBuildEvent>')

    dicts = findings_to_dicts(inspect_projects([ruta], workspace_root=str(tmp_path)))

    assert set(dicts[0].keys()) == {"kind", "severity", "file", "detail"}


def test_sin_llm_ni_red():
    fuente = (ROOT / "services" / "post_build_inspector.py").read_text(encoding="utf-8")
    imports = [ln for ln in fuente.splitlines() if ln.strip().startswith(("import ", "from "))]

    for prohibido in ("requests", "urllib", "copilot", "llm"):
        assert not any(prohibido in ln for ln in imports)
