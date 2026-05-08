"""
lint_scope — T8 Fase 2: Scope Guard.

Verifica que los archivos modificados en el diff estén dentro del scope
definido por `TAREAS_DESARROLLO.md` del ticket. Implementa R9 (fix quirúrgico)
de manera determinística.

Reglas:
  - Cada archivo en el diff debe corresponderse con uno mencionado en
    TAREAS_DESARROLLO.md (matching tolerante: por nombre de archivo si no hay
    path completo).
  - Archivos out-of-scope → ADVERTENCIA por archivo.
  - Si > 3 archivos out-of-scope → BLOQUEANTE (fix dejó de ser quirúrgico).
  - Override: comentario `# scope-override: motivo` en el ticket o un comentario
    git commit con `[scope-override: motivo]` permite el archivo.
  - Excluye archivos auto-generados, tests, archivos maestros RIDIOMA.

CLI:
    python -m linters.lint_scope --tareas TAREAS_DESARROLLO.md < diff.patch
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from linters.diff_parser import hunks_by_file  # noqa: E402
from linters.findings import Finding, Severity, is_blocking  # noqa: E402


# ── Configuración ────────────────────────────────────────────────────────────

# Patrones de archivo a excluir (no cuentan como out-of-scope ni como scope)
EXCLUDED_PATTERNS = (
    r"\.Designer\.cs$",
    r"\.g\.cs$",
    r"/AssemblyInfo\.cs$",
    r"/obj/",
    r"/bin/",
    r"/packages/",
    r"/Tests?/",
    r"/Test/",
    r"\.Tests?/",
    # Archivos maestros RIDIOMA y catálogos — siempre se tocan, son out-of-scope esperable
    r"600804 - Inserts \w+\.sql$",
)

# Threshold para escalar a BLOQUEANTE
MAX_OUT_OF_SCOPE_BEFORE_BLOQUEANTE = 3

# Regex para extraer paths de archivo del TAREAS_DESARROLLO.md
# Acepta: trunk/.../Foo.cs, `trunk/.../Foo.cs`, **trunk/.../Foo.cs**
_RE_PATH_IN_TAREAS = re.compile(
    r"(?:`|\*\*)?(trunk/[\w\-./]+\.(?:cs|aspx|sql|md|js|ts|json|xml))(?:`|\*\*)?",
    re.IGNORECASE,
)
# Si el ticket menciona solo el nombre del archivo (sin path), también lo capturamos
_RE_BARE_FILENAME = re.compile(
    r"(?:`|\*\*)?([A-Z][\w\-]*\.(?:cs|aspx|sql))(?:`|\*\*)?",
)

_RE_OVERRIDE = re.compile(r"#\s*scope-override:\s*(.+)$", re.MULTILINE)


# ── API pública ──────────────────────────────────────────────────────────────

def lint_scope(diff_text: str, tareas_text: str) -> list[Finding]:
    """
    Detecta archivos del diff que NO están en el scope de TAREAS_DESARROLLO.md.

    Args:
        diff_text: unified diff.
        tareas_text: contenido del archivo TAREAS_DESARROLLO.md.

    Returns:
        list[Finding]:
          - 1 ADVERTENCIA por archivo out-of-scope.
          - 1 BLOQUEANTE adicional si supera el umbral de archivos.
    """
    if not tareas_text or not tareas_text.strip():
        # Sin TAREAS_DESARROLLO no hay scope que validar — no se marca nada
        return []

    # 1. Detectar override global (afecta a todos los archivos del diff)
    overrides = set(_RE_OVERRIDE.findall(tareas_text))

    # 2. Construir el scope: paths completos + nombres de archivo "bare"
    scope_paths = set(_RE_PATH_IN_TAREAS.findall(tareas_text))
    scope_filenames = set(_RE_BARE_FILENAME.findall(tareas_text))

    # 3. Iterar archivos del diff
    by_file = hunks_by_file(diff_text)
    out_of_scope: list[str] = []

    for file_path in by_file.keys():
        if _is_excluded(file_path):
            continue
        if _is_in_scope(file_path, scope_paths, scope_filenames):
            continue
        out_of_scope.append(file_path)

    findings: list[Finding] = []
    for path in out_of_scope:
        findings.append(Finding(
            rule_id="R9-SCOPE",
            severity=Severity.ADVERTENCIA,
            file=path,
            line=_first_line_of(by_file[path]),
            snippet=f"Archivo modificado fuera del scope de TAREAS_DESARROLLO.md.",
            fix_hint=f"Agregar `{path}` a TAREAS_DESARROLLO.md con justificación, "
                     f"o remover los cambios sobre este archivo. "
                     f"Override: comment `# scope-override: motivo` en TAREAS_DESARROLLO.md.",
            anchor="core_rules.md#r9-fix-quirurgico",
        ))

    # 4. Si supera el umbral, agregar un BLOQUEANTE de resumen
    if len(out_of_scope) > MAX_OUT_OF_SCOPE_BEFORE_BLOQUEANTE and not overrides:
        findings.append(Finding(
            rule_id="R9-SCOPE",
            severity=Severity.BLOQUEANTE,
            file="(global)",
            line=0,
            snippet=f"{len(out_of_scope)} archivos fuera del scope (umbral={MAX_OUT_OF_SCOPE_BEFORE_BLOQUEANTE}).",
            fix_hint="El fix dejó de ser quirúrgico. Revisar con PM si "
                     "TAREAS_DESARROLLO.md debe expandirse o el cambio dividirse en tickets.",
            anchor="core_rules.md#r9-fix-quirurgico",
        ))

    findings.sort(key=lambda f: (f.file, f.line, f.rule_id))
    return findings


def _is_excluded(path: str) -> bool:
    return any(re.search(p, path) for p in EXCLUDED_PATTERNS)


def _is_in_scope(file_path: str, scope_paths: set[str], scope_filenames: set[str]) -> bool:
    """
    Match con prioridad:
      1. Path completo en scope_paths (match exacto o sufijo).
      2. Si NO hay path completo en scope_paths que use ese mismo basename,
         entonces aceptar match por basename solo (cuando TAREAS menciona
         "Foo.cs" sin path).

    Esto evita falso negativo cuando TAREAS dice `RSFac/Cliente.cs` y el diff
    toca `RSDalc/Cliente.cs` — ambos con basename `Cliente.cs`, pero solo
    el primero está autorizado.
    """
    normalized = file_path.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    scope_paths_normalized = {sp.replace("\\", "/") for sp in scope_paths}

    # 1. Match por path completo
    for sp_norm in scope_paths_normalized:
        if normalized == sp_norm or normalized.endswith("/" + sp_norm.lstrip("/")):
            return True

    # 2. Match por basename — solo si el basename no aparece en scope_paths
    #    con un path distinto. Si aparece, el match por basename es ambiguo y
    #    debe exigirse path completo.
    basename_in_scope_paths = any(
        sp.rsplit("/", 1)[-1] == basename for sp in scope_paths_normalized
    )
    if basename_in_scope_paths:
        return False  # exigir path completo

    if basename in scope_filenames:
        return True

    return False


def _first_line_of(hunks) -> int:
    for h in hunks:
        for a in h.added:
            return a.line_no
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T8 Scope Guard — Fase 2.")
    parser.add_argument("--diff-file", default="-", help="'-' = stdin.")
    parser.add_argument("--tareas", required=True, help="Path a TAREAS_DESARROLLO.md.")
    parser.add_argument("--format", choices=("json", "human"), default="human")
    args = parser.parse_args(argv)

    if args.diff_file == "-":
        diff_text = sys.stdin.read()
    else:
        diff_text = Path(args.diff_file).read_text(encoding="utf-8", errors="replace")

    tareas_path = Path(args.tareas)
    if not tareas_path.exists():
        print(f"[lint-scope] error: TAREAS_DESARROLLO.md no encontrado en {args.tareas}", file=sys.stderr)
        return 2
    tareas_text = tareas_path.read_text(encoding="utf-8", errors="replace")

    findings = lint_scope(diff_text, tareas_text)

    if args.format == "json":
        print(json.dumps([f.to_dict() for f in findings], indent=2, ensure_ascii=False))
    else:
        if not findings:
            print("[lint-scope] ✓ todos los archivos están en scope.", file=sys.stderr)
        else:
            print(f"[lint-scope] {len(findings)} hallazgo(s):", file=sys.stderr)
            for f in findings:
                print(f"  {'✗' if f.severity == Severity.BLOQUEANTE else '!'} "
                      f"[{f.rule_id}] {f.file}:{f.line} — {f.snippet}", file=sys.stderr)

    return 1 if is_blocking(findings) else 0


if __name__ == "__main__":
    sys.exit(main())
