"""
lint_dalc_inchost — T9 Fase 2: detector de inconsistencias entre DDL y Dalc Inchost.

Cuando el diff agrega una columna a una tabla core de Pacífico mediante DDL
(`ALTER TABLE TABLA ADD COL ...`), este linter exige que el Dalc de carga
correspondiente (mapping en `Agentes/shared/glossary_pacifico.md#dalcs-inchost`)
también esté en el diff con `INSERT` y `UPDATE` que mencionen la nueva columna.

Sin esta regla, el campo nuevo nunca se cargaría desde la interfaz Inchost
aunque exista en la tabla — bug histórico recurrente del proyecto (PAC-DALC-1/2/3).

Mapping resuelto en runtime parseando la sección `dalcs-inchost` del glossary.
Si la sección no se encuentra, se usa un fallback hardcoded.

CLI:
    python -m linters.lint_dalc_inchost < diff.patch
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

from linters.diff_parser import parse_diff, hunks_by_file  # noqa: E402
from linters.findings import Finding, Severity, is_blocking  # noqa: E402


# ── Mapping fallback (si no se puede parsear el glossary) ────────────────────

DEFAULT_TABLE_TO_DALC = {
    "RCLIE":      "ClientesDalc.cs",
    "ROBLG":      "ObligacionesDalc.cs",
    "RDEUDA":     "DeudasDalc.cs",
    "RCUOTAS":    "CuotasDalc.cs",
    "RPAGOS":     "PagosDalc.cs",
    "RDIRE":      "DireccionesDalc.cs",
    "RTELE":      "TelefonosDalc.cs",
    "RMAILS":     "MailsDalc.cs",
    "RGARANTIAS": "GarantiasDalc.cs",
    "RCYO":       "RelacionesDalc.cs",
}

DEFAULT_GLOSSARY_PATH = "Agentes/shared/glossary_pacifico.md"


# ── Regex ────────────────────────────────────────────────────────────────────

_RE_ALTER_TABLE_ADD = re.compile(
    r"\bALTER\s+TABLE\s+(\w+)\s+ADD\s+(?:COLUMN\s+)?(\w+)\b",
    re.IGNORECASE,
)
# Captura la tabla y la primera columna agregada. Para cambios "ADD col1, col2"
# el cumplimiento requiere parsing más fino (Fase 4); por ahora marcamos la primera.

_RE_INSERT_INTO = re.compile(
    r'\bINSERT\s+(?:INTO\s+)?(\w+)\b',
    re.IGNORECASE,
)
_RE_UPDATE_TABLE = re.compile(
    r'\bUPDATE\s+(\w+)\s+SET\b',
    re.IGNORECASE,
)


# ── Parser del glossary ──────────────────────────────────────────────────────

def load_table_to_dalc(glossary_path: str | None = None) -> dict[str, str]:
    """
    Parsea la sección `Dalcs Inchost` del glossary y devuelve {tabla: dalc_filename}.
    Fallback al hardcoded si el archivo no existe o el parseo falla.
    """
    if glossary_path is None:
        glossary_path = _resolve_glossary_path()
    p = Path(glossary_path)
    if not p.exists():
        return dict(DEFAULT_TABLE_TO_DALC)
    text = p.read_text(encoding="utf-8", errors="replace")
    # La sección que nos interesa: tabla con header `| Interfaz | Dalc | Tabla destino |`
    # y filas con `| In_X | XxxDalc.cs | TABLA |`
    mapping: dict[str, str] = {}
    in_section = False
    for line in text.split("\n"):
        if "<!-- anchor: dalcs-inchost -->" in line:
            in_section = True
            continue
        if in_section and line.startswith("##"):
            # Salimos de la sección al encontrar el siguiente heading
            break
        if not in_section:
            continue
        # Match filas tipo `| In_Clie | ClientesDalc.cs | RCLIE |`
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) >= 3:
            dalc, table = cols[1], cols[2]
            # Filtrar headers / separadores
            if dalc.endswith("Dalc.cs") and re.match(r"^[A-Z][A-Z0-9_]+$", table):
                mapping[table] = dalc
    if not mapping:
        return dict(DEFAULT_TABLE_TO_DALC)
    return mapping


def _resolve_glossary_path() -> str:
    """Busca el glossary subiendo desde este archivo hasta la raíz del repo."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / DEFAULT_GLOSSARY_PATH
        if candidate.exists():
            return str(candidate)
    return DEFAULT_GLOSSARY_PATH  # devolverá un path inexistente, load() hace fallback


# ── API pública ──────────────────────────────────────────────────────────────

def lint_dalc_consistency(diff_text: str, glossary_path: str | None = None) -> list[Finding]:
    """
    Detecta:
      - Tablas con `ALTER TABLE ... ADD COL` cuyo Dalc Inchost NO está en el diff.
      - Dalc Inchost en el diff cuyo INSERT no menciona la columna nueva.
      - Dalc Inchost en el diff cuyo UPDATE no menciona la columna nueva.

    Args:
        diff_text: unified diff.
        glossary_path: path al glossary; default = autodetect.

    Returns:
        list[Finding] ordenada por archivo y línea.
    """
    table_to_dalc = load_table_to_dalc(glossary_path)
    by_file = hunks_by_file(diff_text)
    findings: list[Finding] = []

    # 1. Buscar ALTER TABLE ADD en cualquier archivo del diff (típicamente .sql)
    additions: list[tuple[str, str, str, int]] = []
    # tuples (table, column, sql_file, line_no)
    for file_path, hunks in by_file.items():
        for hunk in hunks:
            for added in hunk.added:
                m = _RE_ALTER_TABLE_ADD.search(added.content)
                if m:
                    table = m.group(1).upper()
                    column = m.group(2).upper()
                    if table in table_to_dalc:
                        additions.append((table, column, file_path, added.line_no))

    if not additions:
        return findings

    # 2. Para cada columna agregada, verificar que el Dalc correspondiente
    #    esté en el diff y mencione la columna.
    diff_files = list(by_file.keys())

    for table, column, ddl_file, ddl_line in additions:
        dalc_filename = table_to_dalc[table]
        # Buscar el archivo del Dalc en el diff (matching por sufijo del path)
        dalc_files = [f for f in diff_files if f.replace("\\", "/").endswith(dalc_filename)]
        if not dalc_files:
            findings.append(Finding(
                rule_id="PAC-DALC-1",
                severity=Severity.BLOQUEANTE,
                file=ddl_file,
                line=ddl_line,
                snippet=f"ALTER TABLE {table} ADD {column}",
                fix_hint=f"El Dalc Inchost `{dalc_filename}` debe estar en el diff "
                         f"con INSERT y UPDATE actualizados para incluir `{column}`. "
                         f"Si no, la columna nunca se cargará desde la interfaz.",
                anchor="glossary_pacifico.md#dalcs-inchost",
            ))
            continue

        # 3. El Dalc está en el diff. Verificar INSERT/UPDATE menciona la columna.
        dalc_content = _collect_added_text(by_file[dalc_files[0]])
        # Buscar INSERT INTO TABLA dentro del Dalc
        if not _column_in_insert(dalc_content, table, column):
            findings.append(Finding(
                rule_id="PAC-DALC-2",
                severity=Severity.BLOQUEANTE,
                file=dalc_files[0],
                line=_first_line_of(by_file[dalc_files[0]]),
                snippet=f"INSERT no incluye `{column}`",
                fix_hint=f"Agregar la columna `{column}` al `INSERT INTO {table}` "
                         f"en `{dalc_filename}` (lista de columnas + lista de valores + "
                         f"AgregarParametro).",
                anchor="glossary_pacifico.md#dalcs-inchost",
            ))
        if not _column_in_update(dalc_content, table, column):
            findings.append(Finding(
                rule_id="PAC-DALC-3",
                severity=Severity.BLOQUEANTE,
                file=dalc_files[0],
                line=_first_line_of(by_file[dalc_files[0]]),
                snippet=f"UPDATE no incluye `{column}`",
                fix_hint=f"Agregar la columna `{column}` al `UPDATE {table} SET ...` "
                         f"en `{dalc_filename}`.",
                anchor="glossary_pacifico.md#dalcs-inchost",
            ))

    findings.sort(key=lambda f: (f.file, f.line, f.rule_id))
    return findings


# ── Helpers ──────────────────────────────────────────────────────────────────

def _collect_added_text(hunks) -> str:
    return "\n".join(a.content for h in hunks for a in h.added)


def _first_line_of(hunks) -> int:
    for h in hunks:
        for a in h.added:
            return a.line_no
    return 0


def _column_in_insert(text: str, table: str, column: str) -> bool:
    """¿Hay un INSERT INTO TABLE que mencione la columna en sus textos?"""
    # Buscar bloques `INSERT INTO TABLA` y verificar que la columna aparezca cerca.
    upper = text.upper()
    table_upper = table.upper()
    column_upper = column.upper()
    # Localizar todas las ocurrencias de "INSERT" cerca del nombre de la tabla
    found_insert = False
    for m in _RE_INSERT_INTO.finditer(text):
        candidate_table = m.group(1).upper()
        if candidate_table == table_upper:
            found_insert = True
            # Mirar 500 caracteres post-match (suele alcanzar para la lista de columnas)
            window = text[m.start(): m.start() + 500].upper()
            if column_upper in window:
                return True
    if not found_insert:
        # Si no hay un INSERT INTO TABLA literal, podemos chequear que la columna
        # aparezca en el archivo (los Dalcs construyen SQL con concat)
        return column_upper in upper
    return False


def _column_in_update(text: str, table: str, column: str) -> bool:
    """¿Hay un UPDATE TABLE SET que mencione la columna?"""
    upper = text.upper()
    column_upper = column.upper()
    table_upper = table.upper()
    found_update = False
    for m in _RE_UPDATE_TABLE.finditer(text):
        candidate_table = m.group(1).upper()
        if candidate_table == table_upper:
            found_update = True
            window = text[m.start(): m.start() + 500].upper()
            if column_upper in window:
                return True
    if not found_update:
        return column_upper in upper
    return False


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T9 Cross-Module Dalc Linker — Fase 2.")
    parser.add_argument("--diff-file", default="-", help="'-' = stdin.")
    parser.add_argument("--glossary", default=None, help="Path al glossary; auto-detect por default.")
    parser.add_argument("--format", choices=("json", "human"), default="human")
    args = parser.parse_args(argv)

    if args.diff_file == "-":
        diff_text = sys.stdin.read()
    else:
        diff_text = Path(args.diff_file).read_text(encoding="utf-8", errors="replace")

    findings = lint_dalc_consistency(diff_text, glossary_path=args.glossary)

    if args.format == "json":
        print(json.dumps([f.to_dict() for f in findings], indent=2, ensure_ascii=False))
    else:
        if not findings:
            print("[lint-dalc-inchost] ✓ sin inconsistencias.", file=sys.stderr)
        else:
            print(f"[lint-dalc-inchost] {len(findings)} inconsistencia(s):", file=sys.stderr)
            for f in findings:
                print(f"  ✗ [{f.rule_id}] {f.file}:{f.line} — {f.snippet}", file=sys.stderr)
                print(f"      → {f.fix_hint}", file=sys.stderr)

    return 1 if is_blocking(findings) else 0


if __name__ == "__main__":
    sys.exit(main())
