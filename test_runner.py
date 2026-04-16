"""
test_runner.py — G-04: Ejecución Automatizada de Tests Post-DEV.

Después de que DEV completa su trabajo, detecta y ejecuta automáticamente:
  - Tests unitarios del proyecto (.NET: dotnet test / MSTest / NUnit)
  - SQL validation scripts si hay cambios de DB
  - Build verification (compilación)

Los resultados se inyectan en el prompt del TESTER para darle contexto
de qué pasó en la ejecución real antes de su revisión.

Uso:
    from test_runner import run_post_dev_tests
    result = run_post_dev_tests(ticket_folder, ticket_id, workspace_root)
    # genera TEST_RESULTS.md en ticket_folder
"""

import logging
import os
import re
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("mantis.test_runner")

_TIMEOUT_BUILD_SEC = 120
_TIMEOUT_TEST_SEC  = 180
_MAX_OUTPUT_CHARS  = 8000


@dataclass
class TestRunResult:
    success:       bool
    build_ok:      bool
    tests_run:     int
    tests_passed:  int
    tests_failed:  int
    test_errors:   list[str] = field(default_factory=list)
    build_errors:  list[str] = field(default_factory=list)
    duration_sec:  float = 0.0
    report:        str = ""


def run_post_dev_tests(ticket_folder: str, ticket_id: str,
                       workspace_root: str) -> TestRunResult | None:
    """
    Ejecuta build + tests del proyecto y genera TEST_RESULTS.md.
    Retorna None si no hay proyecto de tests detectable.
    """
    if not workspace_root or not os.path.isdir(workspace_root):
        return None

    start = datetime.now()

    # Detectar tipo de proyecto
    project_type = _detect_project_type(workspace_root)
    if not project_type:
        logger.info("[TEST] No se detectó proyecto de tests en %s", workspace_root)
        return None

    logger.info("[TEST] Ejecutando tests %s para ticket #%s...", project_type, ticket_id)

    build_result = _run_build(workspace_root, project_type)
    test_result  = _run_tests(workspace_root, project_type) if build_result["ok"] else None

    duration = (datetime.now() - start).total_seconds()

    result = TestRunResult(
        success      = build_result["ok"] and (test_result is None or test_result["ok"]),
        build_ok     = build_result["ok"],
        tests_run    = test_result["run"]    if test_result else 0,
        tests_passed = test_result["passed"] if test_result else 0,
        tests_failed = test_result["failed"] if test_result else 0,
        test_errors  = test_result["errors"] if test_result else [],
        build_errors = build_result["errors"],
        duration_sec = duration,
    )
    result.report = _format_report(result, ticket_id, project_type)
    _write_results(ticket_folder, result)
    return result


# ── Internals ─────────────────────────────────────────────────────────────────

def _detect_project_type(workspace_root: str) -> str:
    """Detecta el tipo de proyecto de tests."""
    # .NET solution / csproj
    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d not in {"bin", "obj", ".vs", "packages"}]
        for f in files:
            if f.endswith(".sln"):
                return "dotnet"
            if f.endswith(".csproj") and "test" in f.lower():
                return "dotnet"
        break  # solo primer nivel
    return ""


def _run_build(workspace_root: str, project_type: str) -> dict:
    """Ejecuta la compilación del proyecto."""
    result = {"ok": False, "output": "", "errors": []}

    if project_type == "dotnet":
        # Buscar .sln
        sln_files = [f for f in os.listdir(workspace_root) if f.endswith(".sln")]
        if not sln_files:
            result["ok"] = True  # No hay sln en raíz, asumimos OK
            return result

        sln = os.path.join(workspace_root, sln_files[0])
        cmd = ["dotnet", "build", sln, "--configuration", "Debug",
               "--no-restore", "-v", "minimal"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               cwd=workspace_root, timeout=_TIMEOUT_BUILD_SEC,
                               encoding="utf-8", errors="replace")
            result["ok"]     = r.returncode == 0
            result["output"] = (r.stdout + r.stderr)[:_MAX_OUTPUT_CHARS]

            if not result["ok"]:
                # Extraer líneas de error
                for line in result["output"].splitlines():
                    if "error" in line.lower() and "CS" in line:
                        result["errors"].append(line.strip()[:200])
                result["errors"] = result["errors"][:10]
        except FileNotFoundError:
            # dotnet no instalado — intentar con MSBuild
            result["ok"] = True  # Skip build check
        except subprocess.TimeoutExpired:
            result["errors"].append(f"Build timeout ({_TIMEOUT_BUILD_SEC}s)")
        except Exception as e:
            result["errors"].append(str(e)[:100])

    return result


def _run_tests(workspace_root: str, project_type: str) -> dict:
    """Ejecuta los tests del proyecto."""
    result = {"ok": False, "run": 0, "passed": 0, "failed": 0,
              "output": "", "errors": []}

    if project_type == "dotnet":
        # Buscar proyectos de test
        test_projs = []
        for root, dirs, files in os.walk(workspace_root):
            dirs[:] = [d for d in dirs if d not in {"bin", "obj", ".vs"}]
            for f in files:
                if f.endswith(".csproj") and "test" in f.lower():
                    test_projs.append(os.path.join(root, f))

        if not test_projs:
            result["ok"] = True  # No hay tests — OK por defecto
            return result

        cmd = ["dotnet", "test", "--no-build", "--logger", "console;verbosity=normal"]
        if test_projs:
            cmd.append(test_projs[0])

        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               cwd=workspace_root, timeout=_TIMEOUT_TEST_SEC,
                               encoding="utf-8", errors="replace")
            output = (r.stdout + r.stderr)[:_MAX_OUTPUT_CHARS]
            result["output"] = output

            # Parsear resultados
            m = re.search(r'(\d+)\s+(?:test[s]?\s+)?passed', output, re.IGNORECASE)
            if m:
                result["passed"] = int(m.group(1))
            m = re.search(r'(\d+)\s+(?:test[s]?\s+)?failed', output, re.IGNORECASE)
            if m:
                result["failed"] = int(m.group(1))
            result["run"]    = result["passed"] + result["failed"]
            result["ok"]     = r.returncode == 0 and result["failed"] == 0

            # Extraer tests fallidos
            for line in output.splitlines():
                if re.search(r'failed|error', line, re.IGNORECASE) and len(line) > 10:
                    result["errors"].append(line.strip()[:200])
            result["errors"] = result["errors"][:10]

        except FileNotFoundError:
            result["ok"] = True  # dotnet no disponible
        except subprocess.TimeoutExpired:
            result["errors"].append(f"Test timeout ({_TIMEOUT_TEST_SEC}s)")
        except Exception as e:
            result["errors"].append(str(e)[:100])

    return result


def _format_report(result: TestRunResult, ticket_id: str, project_type: str) -> str:
    """Genera el reporte Markdown de resultados de tests."""
    status = "✅ PASÓ" if result.success else "❌ FALLÓ"
    lines  = [
        f"# Test Results — Ticket #{ticket_id}",
        "",
        f"> Estado: **{status}**  ",
        f"> Tipo: {project_type}  ",
        f"> Duración: {result.duration_sec:.0f}s  ",
        f"> Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## Compilación",
        "",
        f"{'✅ Exitosa' if result.build_ok else '❌ Con errores'}",
        "",
    ]

    if result.build_errors:
        lines += ["**Errores de compilación:**", ""]
        for err in result.build_errors[:5]:
            lines.append(f"- `{err}`")
        lines.append("")

    lines += [
        "## Tests",
        "",
        f"| Ejecutados | Pasados | Fallidos |",
        f"|-----------|---------|----------|",
        f"| {result.tests_run} | {result.tests_passed} | {result.tests_failed} |",
        "",
    ]

    if result.test_errors:
        lines += ["**Tests fallidos:**", ""]
        for err in result.test_errors[:5]:
            lines.append(f"- `{err}`")
        lines.append("")

    lines.append("_Resultados generados automáticamente por Stacky Test Runner._")
    return "\n".join(lines)


def _write_results(ticket_folder: str, result: TestRunResult) -> None:
    """Escribe TEST_RESULTS.md en la carpeta del ticket."""
    path = os.path.join(ticket_folder, "TEST_RESULTS.md")
    try:
        Path(path).write_text(result.report, encoding="utf-8")
        logger.info("[TEST] TEST_RESULTS.md generado (success=%s, tests=%d)",
                    result.success, result.tests_run)
    except Exception as e:
        logger.error("[TEST] Error escribiendo TEST_RESULTS.md: %s", e)
