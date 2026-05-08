#!/usr/bin/env python3
"""
build.py — Compilador de soluciones RS Pacífico via MSBuild
Sin servidor, sin dependencias externas — solo Python 3.8+ stdlib.

ACCIONES:
  compile    Compila una solución o proyecto con MSBuild
  list       Lista las soluciones disponibles por sistema

SALIDA: siempre JSON a stdout
ERRORES: JSON a stdout con "ok": false  +  exit code 1

Si la compilación falla (errores de MSBuild) → exit code 1 + "build_success": false
Si la compilación es exitosa → exit code 0 + "build_success": true

CONFIGURACIÓN (en orden de prioridad):
  1. Args CLI: --msbuild
  2. build-config.json en la misma carpeta que este script

EJEMPLOS:
  python build.py list
  python build.py list --system online
  python build.py list --system batch
  python build.py compile --system online --solution AgendaWeb
  python build.py compile --system batch --solution Motor
  python build.py compile --solution "n:/GIT/RS/RSPacifico/trunk/OnLine/Soluciones/AgendaWeb.sln"
  python build.py compile --system online --solution AgendaWeb --config Debug
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# ─── CONFIG ──────────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent

_DEFAULT_MSBUILD_PATHS = [
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
    r"C:\Program Files\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\MSBuild.exe",
    r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\MSBuild.exe",
    r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\MSBuild\Current\Bin\MSBuild.exe",
    r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\MSBuild\Current\Bin\MSBuild.exe",
    r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Enterprise\MSBuild\Current\Bin\MSBuild.exe",
]

# Rutas base del repo (relativas al repo root, que es 3 niveles arriba de este script)
_REPO_ROOT = (_SCRIPT_DIR / "../../../..").resolve()
_ONLINE_SLN_DIR = _REPO_ROOT / "trunk" / "OnLine" / "Soluciones"
_BATCH_SLN_DIR  = _REPO_ROOT / "trunk" / "Batch"  / "Soluciones"


def _load_config() -> dict:
    """Lee build-config.json → dict vacío si no existe."""
    cfg_path = _SCRIPT_DIR / "build-config.json"
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _find_msbuild(cfg: dict) -> Path | None:
    """Busca MSBuild en config → variables de entorno → rutas conocidas."""
    # 1. Config
    if cfg.get("msbuild"):
        p = Path(cfg["msbuild"])
        if p.exists():
            return p

    # 2. Rutas predeterminadas
    for path_str in _DEFAULT_MSBUILD_PATHS:
        p = Path(path_str)
        if p.exists():
            return p

    return None


def _ok(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    sys.exit(0)


def _err(msg: str, **extra: Any) -> None:
    print(json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False, indent=2))
    sys.exit(1)


# ─── DESCUBRIMIENTO DE SOLUCIONES ────────────────────────────────────────────

def _discover_solutions(system: str | None = None) -> dict[str, list[dict]]:
    """Descubre los .sln disponibles en las carpetas de soluciones."""
    result: dict[str, list[dict]] = {}

    def _scan(base_dir: Path, system_name: str) -> list[dict]:
        items = []
        if not base_dir.exists():
            return items
        for sln in sorted(base_dir.glob("*.sln")):
            items.append({
                "name": sln.stem,
                "file": sln.name,
                "path": str(sln),
                "system": system_name,
            })
        return items

    if system in (None, "online"):
        result["online"] = _scan(_ONLINE_SLN_DIR, "online")
    if system in (None, "batch"):
        result["batch"] = _scan(_BATCH_SLN_DIR, "batch")

    return result


def _resolve_solution_path(system: str | None, solution: str) -> Path:
    """
    Resuelve la ruta al .sln dado un nombre o ruta completa.
    Si 'solution' es una ruta absoluta/relativa existente → usarla directamente.
    Si no, buscar por nombre en la carpeta del sistema indicado.
    """
    # Ruta directa
    p = Path(solution)
    if p.exists():
        return p.resolve()

    # Agregar extensión si falta
    if not solution.lower().endswith(".sln"):
        solution_with_ext = solution + ".sln"
    else:
        solution_with_ext = solution

    # Buscar en directorio del sistema
    if system == "online":
        candidate = _ONLINE_SLN_DIR / solution_with_ext
        if candidate.exists():
            return candidate.resolve()
    elif system == "batch":
        candidate = _BATCH_SLN_DIR / solution_with_ext
        if candidate.exists():
            return candidate.resolve()
    else:
        # Buscar en ambos
        for base in [_ONLINE_SLN_DIR, _BATCH_SLN_DIR]:
            candidate = base / solution_with_ext
            if candidate.exists():
                return candidate.resolve()

    return None


# ─── PARSEO DE OUTPUT MSBUILD ─────────────────────────────────────────────────

_ERROR_RE   = re.compile(r"(?i)\berror\b\s+\w+\d+\s*:", re.MULTILINE)
_WARNING_RE = re.compile(r"(?i)\bwarning\b\s+\w+\d+\s*:", re.MULTILINE)

# Formato de línea de error/warning MSBuild:
#   archivo(linea,col): error CS0000: mensaje
_DIAG_LINE_RE = re.compile(
    r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\)\s*:\s*"
    r"(?P<level>error|warning)\s+(?P<code>\w+\d+)\s*:\s*(?P<message>.+)$",
    re.IGNORECASE | re.MULTILINE,
)

# Línea final: "Build succeeded." / "Error(s)" / "n Error(s)"
_BUILD_RESULT_RE = re.compile(
    r"Build\s+(?P<result>succeeded|FAILED)\.",
    re.IGNORECASE,
)
_ERROR_COUNT_RE   = re.compile(r"(\d+)\s+Error\(s\)",   re.IGNORECASE)
_WARNING_COUNT_RE = re.compile(r"(\d+)\s+Warning\(s\)", re.IGNORECASE)


def _parse_msbuild_output(output: str) -> dict:
    """
    Parsea la salida de MSBuild y extrae:
    - build_success (bool)
    - errors (list de dicts)
    - warnings (list de dicts)
    - error_count (int)
    - warning_count (int)
    - summary (str) — última línea relevante
    """
    errors: list[dict]   = []
    warnings: list[dict] = []

    for match in _DIAG_LINE_RE.finditer(output):
        entry = {
            "file":    match.group("file").strip(),
            "line":    int(match.group("line")),
            "col":     int(match.group("col")),
            "code":    match.group("code"),
            "message": match.group("message").strip(),
        }
        if match.group("level").lower() == "error":
            errors.append(entry)
        else:
            warnings.append(entry)

    # Detectar resultado final
    result_match = _BUILD_RESULT_RE.search(output)
    build_success = (
        result_match is not None and
        result_match.group("result").lower() == "succeeded"
    )

    # Contar desde el resumen de MSBuild (más confiable que el parseo de líneas)
    err_count_match  = _ERROR_COUNT_RE.search(output)
    warn_count_match = _WARNING_COUNT_RE.search(output)
    error_count   = int(err_count_match.group(1))   if err_count_match   else len(errors)
    warning_count = int(warn_count_match.group(1))  if warn_count_match  else len(warnings)

    # Extraer las últimas 6 líneas no vacías como resumen
    lines = [l for l in output.splitlines() if l.strip()]
    summary_lines = lines[-6:] if len(lines) >= 6 else lines
    summary = "\n".join(summary_lines)

    return {
        "build_success": build_success,
        "error_count":   error_count,
        "warning_count": warning_count,
        "errors":        errors,
        "warnings":      warnings,
        "summary":       summary,
    }


# ─── ACCIONES ────────────────────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace, cfg: dict) -> None:
    system = getattr(args, "system", None)
    solutions = _discover_solutions(system)

    total = sum(len(v) for v in solutions.values())
    _ok({
        "ok": True,
        "action": "list",
        "total": total,
        "solutions": solutions,
    })


def cmd_compile(args: argparse.Namespace, cfg: dict) -> None:
    msbuild = _find_msbuild(cfg)
    if msbuild is None:
        _err(
            "MSBuild.exe no encontrado. Verificá que Visual Studio esté instalado "
            "o configurá la ruta en build-config.json bajo la clave 'msbuild'."
        )

    system   = getattr(args, "system", None)
    solution = getattr(args, "solution", None)
    config   = getattr(args, "config", "Release")

    if not solution:
        _err("Debes especificar --solution <nombre o ruta>")

    sln_path = _resolve_solution_path(system, solution)
    if sln_path is None:
        _err(
            f"No se encontró la solución '{solution}'.",
            hint=(
                f"Usá 'python build.py list --system {system or 'online|batch'}' "
                f"para ver las soluciones disponibles."
            ),
        )

    # Determinar sistema a partir de la ruta si no fue especificado
    if system is None:
        path_str = str(sln_path).lower()
        if "\\online\\" in path_str or "/online/" in path_str:
            system = "online"
        elif "\\batch\\" in path_str or "/batch/" in path_str:
            system = "batch"
        else:
            system = "unknown"

    cmd = [
        str(msbuild),
        str(sln_path),
        f"/p:Configuration={config}",
        "/t:Rebuild",
        "/v:minimal",
        "/nologo",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,  # 10 min máx
        )
    except FileNotFoundError:
        _err(f"MSBuild no encontrado en la ruta: {msbuild}")
    except subprocess.TimeoutExpired:
        _err("MSBuild superó el tiempo máximo de 10 minutos.")
    except Exception as exc:
        _err(f"Error al ejecutar MSBuild: {exc}")

    full_output = proc.stdout + proc.stderr
    parsed = _parse_msbuild_output(full_output)

    result = {
        "ok":            parsed["build_success"],
        "action":        "compile",
        "build_success": parsed["build_success"],
        "system":        system,
        "solution":      sln_path.name,
        "solution_path": str(sln_path),
        "config":        config,
        "msbuild":       str(msbuild),
        "exit_code":     proc.returncode,
        "error_count":   parsed["error_count"],
        "warning_count": parsed["warning_count"],
        "errors":        parsed["errors"],
        "warnings":      parsed["warnings"],
        "summary":       parsed["summary"],
    }

    if not parsed["build_success"]:
        result["recommendation"] = (
            "Corregí todos los errores listados en 'errors' y volvé a compilar. "
            "NO crees commit, push ni PR hasta obtener build_success: true."
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if parsed["build_success"] else 1)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build.py",
        description="Compilador de soluciones RS Pacífico via MSBuild. Salida siempre JSON.",
    )
    sub = parser.add_subparsers(dest="action", required=True)

    # list
    p_list = sub.add_parser("list", help="Lista soluciones disponibles")
    p_list.add_argument(
        "--system",
        choices=["online", "batch"],
        help="Filtrar por sistema (online | batch). Sin filtro muestra todos.",
    )

    # compile
    p_compile = sub.add_parser("compile", help="Compila una solución con MSBuild")
    p_compile.add_argument(
        "--system",
        choices=["online", "batch"],
        help="Sistema al que pertenece la solución (online | batch).",
    )
    p_compile.add_argument(
        "--solution",
        required=True,
        help=(
            "Nombre de la solución (sin .sln) o ruta absoluta al archivo .sln. "
            "Ejemplos: AgendaWeb | Motor | n:/ruta/Solucion.sln"
        ),
    )
    p_compile.add_argument(
        "--config",
        default="Release",
        help="Configuración de build (Release | Debug). Default: Release.",
    )
    p_compile.add_argument(
        "--msbuild",
        help="Ruta manual a MSBuild.exe (sobreescribe build-config.json).",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    cfg = _load_config()

    # Sobreescribir msbuild desde CLI si fue pasado
    if hasattr(args, "msbuild") and args.msbuild:
        cfg["msbuild"] = args.msbuild

    if args.action == "list":
        cmd_list(args, cfg)
    elif args.action == "compile":
        cmd_compile(args, cfg)
    else:
        _err(f"Acción desconocida: {args.action}")


if __name__ == "__main__":
    main()
