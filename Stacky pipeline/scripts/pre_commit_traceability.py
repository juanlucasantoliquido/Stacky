#!/usr/bin/env python3
"""
pre_commit_traceability — Hook que valida trazabilidad ADO en cambios de código.

Cada hunk staged en archivos .cs/.aspx/.aspx.cs debe tener cerca un comentario
con formato:

    // ADO-{id} | YYYY-MM-DD | descripción

Reemplaza la "responsabilidad" del prompt de DevPacifico de auto-disciplinarse
por una verificación física en el commit.

Uso (manual / debug):
    python scripts/pre_commit_traceability.py

Uso (como pre-commit hook):
    # Opción A: pre-commit framework
    #   .pre-commit-config.yaml apunta a este script
    # Opción B: hook directo
    #   git config core.hooksPath .githooks
    #   .githooks/pre-commit invoca: python Tools/Stacky/.../pre_commit_traceability.py

Bypass (sólo emergencias, dejar audit-trail):
    SKIP_TRACEABILITY=1 git commit -m "..."

Exit codes:
    0 — todo OK (o bypass activo).
    1 — al menos un hunk sin trazabilidad.
    2 — error interno (git diff falló, etc.).

Cubierto por tests/unit/test_pre_commit_traceability.py.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass


# ── Configuración ────────────────────────────────────────────────────────────

# Extensiones cuya trazabilidad se valida
EXTENSIONS = ('.cs', '.aspx', '.aspx.cs', '.ascx', '.ascx.cs')

# Patrones de archivos a ignorar (tests, generated code, etc.)
IGNORE_PATTERNS = (
    r'/Tests?/',
    r'/Test/',
    r'\.Tests?/',
    r'/AssemblyInfo\.cs$',
    r'\.Designer\.cs$',
    r'\.g\.cs$',
    r'/obj/',
    r'/bin/',
    r'/packages/',
    r'/node_modules/',
)

# Regex de trazabilidad. Tolera espacios/tabs y descripciones largas.
TRACEABILITY_RE = re.compile(
    r'//\s*ADO-\d+\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*\S.+'
)

# Líneas mínimas agregadas no-whitespace para exigir trazabilidad
# (un hunk de 1 línea trivial no es necesariamente un cambio sustantivo)
MIN_LINES_FOR_TRACEABILITY = 3

# Cuántas líneas antes del primer added-line buscar el comentario
LOOKBACK_LINES = 5

BYPASS_ENV = 'SKIP_TRACEABILITY'


# ── Modelo ───────────────────────────────────────────────────────────────────

@dataclass
class _Hunk:
    file: str
    start_line: int           # primer línea del hunk en el archivo nuevo
    added_lines: list[str]    # líneas agregadas (sin el `+` inicial)
    context_before: list[str] # líneas de contexto previas (sin marcador)


# ── API pública ──────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    if os.environ.get(BYPASS_ENV) == '1':
        print(f'[pre-commit-traceability] BYPASS activo ({BYPASS_ENV}=1) — saltando.', file=sys.stderr)
        return 0

    try:
        diff = _git_diff_cached()
    except subprocess.CalledProcessError as e:
        print(f'[pre-commit-traceability] git diff falló: {e}', file=sys.stderr)
        return 2

    hunks = list(_parse_diff(diff))
    violations = []

    for hunk in hunks:
        if not _is_relevant_file(hunk.file):
            continue
        if not _has_substantive_changes(hunk):
            continue
        if _has_traceability(hunk):
            continue
        violations.append(hunk)

    if violations:
        _report(violations)
        return 1

    return 0


# ── Internals ────────────────────────────────────────────────────────────────

def _git_diff_cached() -> str:
    result = subprocess.run(
        ['git', 'diff', '--cached', '--no-color', '-U' + str(LOOKBACK_LINES)],
        capture_output=True,
        text=True,
        check=True,
        encoding='utf-8',
        errors='replace',
    )
    return result.stdout


def _is_relevant_file(path: str) -> bool:
    if not path.endswith(EXTENSIONS):
        return False
    for pat in IGNORE_PATTERNS:
        if re.search(pat, path):
            return False
    return True


def _has_substantive_changes(hunk: _Hunk) -> bool:
    non_ws = [l for l in hunk.added_lines if l.strip()]
    return len(non_ws) >= MIN_LINES_FOR_TRACEABILITY


def _has_traceability(hunk: _Hunk) -> bool:
    # Buscar el comentario en líneas agregadas o en las de contexto previas
    lookback = hunk.context_before[-LOOKBACK_LINES:] if hunk.context_before else []
    for line in lookback + hunk.added_lines:
        if TRACEABILITY_RE.search(line):
            return True
    return False


def _parse_diff(diff_text: str):
    """
    Parser minimal de git diff unified. Yield un _Hunk por cada bloque @@.
    """
    current_file: str | None = None
    current_hunk: _Hunk | None = None

    for line in diff_text.split('\n'):
        if line.startswith('+++ b/'):
            current_file = line[len('+++ b/'):]
            continue
        if line.startswith('+++ '):
            # Caso /dev/null (eliminación) — no relevante para trazabilidad
            current_file = None
            continue
        if line.startswith('@@'):
            if current_hunk is not None:
                yield current_hunk
            m = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
            start = int(m.group(1)) if m else 0
            current_hunk = _Hunk(
                file=current_file or '',
                start_line=start,
                added_lines=[],
                context_before=[],
            )
            continue
        if current_hunk is None:
            continue
        if line.startswith('+') and not line.startswith('+++'):
            current_hunk.added_lines.append(line[1:])
        elif line.startswith('-') and not line.startswith('---'):
            # Líneas eliminadas — no afectan trazabilidad
            pass
        elif line.startswith(' '):
            # Línea de contexto
            if not current_hunk.added_lines:
                current_hunk.context_before.append(line[1:])

    if current_hunk is not None:
        yield current_hunk


def _report(violations: list[_Hunk]) -> None:
    print('', file=sys.stderr)
    print('═══ PRE-COMMIT TRAZABILIDAD ADO — VIOLACIONES ═══', file=sys.stderr)
    print('', file=sys.stderr)
    print('Cada hunk de código (≥ 3 líneas modificadas) debe tener cerca un comentario:', file=sys.stderr)
    print('    // ADO-{id} | YYYY-MM-DD | descripción', file=sys.stderr)
    print('', file=sys.stderr)
    for h in violations:
        print(f'  ✗ {h.file}:{h.start_line}', file=sys.stderr)
        preview = next((l for l in h.added_lines if l.strip()), '<vacío>')
        print(f'      primera línea: {preview.rstrip()[:100]}', file=sys.stderr)
    print('', file=sys.stderr)
    print(f'Total: {len(violations)} hunk(s) sin trazabilidad.', file=sys.stderr)
    print('', file=sys.stderr)
    print('Para emergencias (deja log):  SKIP_TRACEABILITY=1 git commit ...', file=sys.stderr)
    print('Convención completa:          Agentes/shared/output_formats.md#traceability', file=sys.stderr)
    print('', file=sys.stderr)


if __name__ == '__main__':
    sys.exit(main())
