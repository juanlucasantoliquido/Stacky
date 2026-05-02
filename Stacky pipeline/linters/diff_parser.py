"""
diff_parser — Parser unified-diff compartido entre linters de Fase 2.

Refactor de la lógica originalmente en `pre_commit_traceability.py` (P1.5).
Provee un modelo `Hunk` con líneas agregadas, contexto previo/posterior, y
mapeo línea→número-en-archivo-nuevo para que cada linter pueda producir
findings con `file:line` precisos.

Uso:

    from linters.diff_parser import parse_diff, Hunk
    for hunk in parse_diff(diff_text):
        print(hunk.file, hunk.start_line, hunk.added_lines)

Soporta:
  - Múltiples archivos por diff.
  - Múltiples hunks por archivo.
  - Eliminaciones puras (added_lines vacío).
  - --- /dev/null para creaciones, +++ /dev/null para borrados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator


_RE_FILE_HEADER_NEW = re.compile(r"^\+\+\+ (?:b/)?(.+?)\s*$")
_RE_HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


@dataclass
class AddedLine:
    """Una línea agregada por el diff, con su número en el archivo nuevo."""
    line_no: int      # número de línea en el archivo post-cambio
    content: str      # contenido sin el `+` inicial


@dataclass
class Hunk:
    file: str
    start_line: int                                    # primera línea del hunk en el archivo nuevo
    added: list[AddedLine] = field(default_factory=list)
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)

    @property
    def added_lines(self) -> list[str]:
        """Compat con `pre_commit_traceability` viejo: lista de strings."""
        return [a.content for a in self.added]

    def added_substantive_count(self) -> int:
        """Cantidad de líneas agregadas con contenido no-whitespace."""
        return sum(1 for a in self.added if a.content.strip())


def parse_diff(diff_text: str) -> Iterator[Hunk]:
    """
    Parsea un unified diff y yieldea un Hunk por cada bloque @@.

    Asume formato `git diff` con `--- a/...` y `+++ b/...`. Tolera diffs sin
    `b/` prefix.
    """
    current_file: str | None = None
    current: Hunk | None = None
    new_line_cursor = 0
    added_seen_in_current = False

    for line in diff_text.split("\n"):
        # Archivo nuevo (file header)
        m = _RE_FILE_HEADER_NEW.match(line)
        if m:
            path = m.group(1)
            current_file = None if path == "/dev/null" else path
            continue

        # Hunk header
        m = _RE_HUNK_HEADER.match(line)
        if m:
            if current is not None:
                yield current
            new_start = int(m.group(3))
            current = Hunk(
                file=current_file or "",
                start_line=new_start,
                added=[],
                context_before=[],
                context_after=[],
            )
            new_line_cursor = new_start
            added_seen_in_current = False
            continue

        if current is None:
            continue

        # Línea agregada
        if line.startswith("+") and not line.startswith("+++"):
            current.added.append(AddedLine(line_no=new_line_cursor, content=line[1:]))
            new_line_cursor += 1
            added_seen_in_current = True
            continue

        # Línea eliminada — no avanza cursor del archivo nuevo
        if line.startswith("-") and not line.startswith("---"):
            continue

        # Línea de contexto (espacio inicial). Avanza cursor.
        if line.startswith(" "):
            content = line[1:]
            if added_seen_in_current:
                current.context_after.append(content)
            else:
                current.context_before.append(content)
            new_line_cursor += 1
            continue

        # Otras líneas (no \ No newline at end of file, header del file, etc.) se ignoran.

    if current is not None:
        yield current


def hunks_by_file(diff_text: str) -> dict[str, list[Hunk]]:
    """Agrupa hunks por path de archivo."""
    out: dict[str, list[Hunk]] = {}
    for h in parse_diff(diff_text):
        if h.file:
            out.setdefault(h.file, []).append(h)
    return out
