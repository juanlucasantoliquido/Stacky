"""
lint_golden_rules — T1 Fase 2: linter sobre diff que detecta violaciones de R1–R10.

Convierte responsabilidades del prompt QA en checks deterministas. La fuente
de verdad de cada regla está en `Agentes/shared/core_rules.md` con anchors
estables que este módulo cita en cada Finding.

Reglas implementadas en P2.1:
  - R2 — `cConexion` solo en Facade (BLOQUEANTE).
  - R3 — Transacciones solo en Facade (BLOQUEANTE).
  - R4 — SQL parametrizado / anti SQL injection (BLOQUEANTE).

Reglas pendientes (P2.2): R1 (RIDIOMA), R10 (verificación post-query).

CLI:
    python -m linters.lint_golden_rules < diff.patch
    python -m linters.lint_golden_rules --rules R2,R4 < diff.patch

Exit code:
    0 — sin BLOQUEANTES (puede haber advisories).
    1 — al menos un BLOQUEANTE.
    2 — error interno (parser falló, etc.).

Allowlist:
    Comentario inline en la línea o en la línea inmediata anterior:
        // golden-rules-disable: R4 — motivo
    suprime ESE finding específico para esa línea.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Permitir import directo (python lint_golden_rules.py) y como módulo
_HERE = Path(__file__).parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from linters.diff_parser import parse_diff, Hunk, AddedLine  # noqa: E402
from linters.findings import Finding, Severity, is_blocking  # noqa: E402


# ── Configuración ────────────────────────────────────────────────────────────

ALL_RULES = ("R1", "R2", "R3", "R4", "R10")

# Extensiones a auditar
CS_EXTENSIONS = (".cs", ".aspx", ".aspx.cs", ".ascx", ".ascx.cs")

# Paths que indican capa Facade (donde cConexion y transacciones SÍ pueden vivir)
FACADE_PATHS = ("/RSFac/", "/RsFac/", "\\RSFac\\")

# Paths que indican capas donde NO debe haber cConexion ni transacciones
BUS_DALC_PATHS = ("/RSBus/", "/RSDalc/", "/RsBus/", "/RsDalc/", "\\RSBus\\", "\\RSDalc\\")

# Orquestadores Batch que pueden crear cConexion (más allá de RSFac)
BATCH_ORCHESTRATOR_FILES = ("Program.cs", "MotorRS.cs", "MotorJ.cs", "MotorRS_J.cs")


# ── Allowlist por linea ─────────────────────────────────────────────────────

_RE_DISABLE = re.compile(r"//\s*golden-rules-disable:\s*([A-Z0-9, ]+)")


def _is_disabled(rule: str, line: str, prev_line: str = "") -> bool:
    """¿Esta línea (o la anterior) tiene un disable para esta regla?"""
    for source in (line, prev_line):
        m = _RE_DISABLE.search(source)
        if not m:
            continue
        rules = [r.strip() for r in m.group(1).split(",")]
        if rule in rules or "ALL" in rules:
            return True
    return False


# ── R2 — cConexion solo en Facade ────────────────────────────────────────────

_RE_NEW_CCONEXION = re.compile(r"\bnew\s+cConexion\s*\(")


def _check_r2_cconexion_in_facade(hunks: list[Hunk]) -> list[Finding]:
    findings: list[Finding] = []
    for hunk in hunks:
        if not hunk.file.endswith(CS_EXTENSIONS):
            continue
        # Si el archivo está en RSFac o es orquestador Batch, no hay violación
        if _is_facade(hunk.file) or _is_batch_orchestrator(hunk.file):
            continue
        # Si NO está en Bus/Dalc, no aplica (no es responsabilidad de R2 monitorearlo)
        if not _is_bus_or_dalc(hunk.file):
            continue
        for i, added in enumerate(hunk.added):
            if not _RE_NEW_CCONEXION.search(added.content):
                continue
            prev = hunk.added[i - 1].content if i > 0 else ""
            if _is_disabled("R2", added.content, prev):
                continue
            findings.append(Finding(
                rule_id="R2",
                severity=Severity.BLOQUEANTE,
                file=hunk.file,
                line=added.line_no,
                snippet=added.content.strip(),
                fix_hint="Mover el `new cConexion()` a un archivo de RSFac/. "
                         "RSBus/RSDalc reciben `conn` por constructor.",
                anchor="core_rules.md#r2-cconexion-facade",
            ))
    return findings


# ── R3 — Transacciones solo en Facade ────────────────────────────────────────

_RE_TRANSACTION_CALL = re.compile(
    r"\b(?:ComienzoTransaccion|CommitTransaccion|RollbackTransaccion)\s*\("
)


def _check_r3_transactions_in_facade(hunks: list[Hunk]) -> list[Finding]:
    findings: list[Finding] = []
    for hunk in hunks:
        if not hunk.file.endswith(CS_EXTENSIONS):
            continue
        if _is_facade(hunk.file) or _is_batch_orchestrator(hunk.file):
            continue
        if not _is_bus_or_dalc(hunk.file):
            continue
        for i, added in enumerate(hunk.added):
            if not _RE_TRANSACTION_CALL.search(added.content):
                continue
            prev = hunk.added[i - 1].content if i > 0 else ""
            if _is_disabled("R3", added.content, prev):
                continue
            findings.append(Finding(
                rule_id="R3",
                severity=Severity.BLOQUEANTE,
                file=hunk.file,
                line=added.line_no,
                snippet=added.content.strip(),
                fix_hint="Mover la apertura/cierre de transacción al RSFac. "
                         "Bus/Dalc no abren ni cierran transacciones.",
                anchor="core_rules.md#r3-transacciones-facade",
            ))
    return findings


# ── R4 — SQL parametrizado / anti SQL injection ──────────────────────────────

# Heurística:
#   1. Detectar líneas con string literal que contiene palabras SQL (SELECT/INSERT/UPDATE/DELETE/MERGE/FROM/WHERE/INTO/SET).
#   2. Si en la misma línea aparece ` + identifier ` (concatenación con variable),
#      es candidato a R4 BLOQUEANTE.
#   3. Concatenación con cadenas que parecen constantes/nombres de tabla
#      (mayúsculas o `Const.`/`enum`) NO se marca.
#   4. El operador de concatenación puede ser `+` o `+=`.

_RE_SQL_KEYWORD_IN_STRING = re.compile(
    r'"[^"\n]*\b(?:SELECT|INSERT|UPDATE|DELETE|MERGE|FROM|WHERE|INTO|SET|VALUES|JOIN)\b[^"\n]*"',
    re.IGNORECASE,
)
_RE_CONCAT_VAR = re.compile(
    r'(?:["\)\]]\s*\+\s*|\+=\s*)([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)'
)
_RE_CONCAT_VAR_TRAILING = re.compile(
    r'(\b[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)\s*\+\s*"'
)

# Identificadores que parecen constantes (no input de usuario): TODO_MAYUSCULAS o Const.X
_RE_CONST_LIKE = re.compile(r"^[A-Z][A-Z0-9_]*$|^Const\.|^Enums?\.|^Constantes?\.")


def _looks_like_const(ident: str) -> bool:
    """¿El identificador concatenado es una constante o nombre técnico?"""
    return bool(_RE_CONST_LIKE.match(ident))


def _check_r4_sql_injection(hunks: list[Hunk]) -> list[Finding]:
    findings: list[Finding] = []
    for hunk in hunks:
        if not hunk.file.endswith(CS_EXTENSIONS):
            continue
        # Mirar tanto líneas agregadas como contexto siguiente para SQL multi-línea
        all_lines = [(a.line_no, a.content) for a in hunk.added]
        for i, (line_no, content) in enumerate(all_lines):
            # ¿Contiene un string SQL?
            if not _RE_SQL_KEYWORD_IN_STRING.search(content):
                continue
            # ¿Concatena con variable que no es constante?
            for match in _RE_CONCAT_VAR.finditer(content):
                ident = match.group(1)
                if _looks_like_const(ident):
                    continue
                if _is_disabled("R4", content, all_lines[i - 1][1] if i > 0 else ""):
                    continue
                findings.append(Finding(
                    rule_id="R4",
                    severity=Severity.BLOQUEANTE,
                    file=hunk.file,
                    line=line_no,
                    snippet=content.strip(),
                    fix_hint=f"Reemplazar `+ {ident}` por parámetro: "
                             f"`@p_xxx` (SQL Server) o `:p_xxx` (Oracle), "
                             f"y `conn.AgregarParametro(\"@p_xxx\", {ident});`.",
                    anchor="core_rules.md#r4-sql-parametrizado",
                ))
                break  # un finding por línea es suficiente
            else:
                # No matchó _RE_CONCAT_VAR — chequear el patrón "var + \"...\"" (variable antes del string)
                m_trailing = _RE_CONCAT_VAR_TRAILING.search(content)
                if m_trailing:
                    ident = m_trailing.group(1)
                    if not _looks_like_const(ident):
                        if not _is_disabled("R4", content, all_lines[i - 1][1] if i > 0 else ""):
                            findings.append(Finding(
                                rule_id="R4",
                                severity=Severity.BLOQUEANTE,
                                file=hunk.file,
                                line=line_no,
                                snippet=content.strip(),
                                fix_hint=f"Reemplazar `{ident} +` por parámetro nominal "
                                         f"(`@p_xxx` / `:p_xxx`).",
                                anchor="core_rules.md#r4-sql-parametrizado",
                            ))
    return findings


# ── R1 — RIDIOMA: cero strings hardcodeados visibles al usuario ──────────────

# Detectar strings literales en contextos donde son mensajes visibles al usuario.
# Versión inicial conservadora: marcamos estos call-sites donde el string NO
# es un coMens.mXXXX o Idm.Texto:
#
#   Error.Agregar(..., "texto", ...)
#   .Errores.AgregarError("texto"...)
#   AgregarError("texto"...)
#   .Text = "texto"     (lblXxx.Text, btnXxx.Text, etc.)
#   .ToolTip = "texto"
#   MostrarMensaje("texto"...)
#   msgd.Show("texto"...)
#
# Excepciones (no marcamos):
#   - El argumento envuelto en Idm.Texto(...) o coMens.*
#   - String vacío "" o whitespace.
#   - Strings que claramente son técnicos (ej: nombres de columna SQL en comillas).

_RE_USER_VISIBLE_LITERAL = re.compile(
    r"""
    (?:
        Error\.Agregar\s*\(                           # Error.Agregar(
        | (?:this\.)?Errores\.AgregarError\s*\(       # Errores.AgregarError(
        | \bAgregarError\s*\(                         # AgregarError(
        | \.Text\s*=\s*                               # .Text =
        | \.ToolTip\s*=\s*                            # .ToolTip =
        | \bMostrarMensaje\s*\(                       # MostrarMensaje(
        | \bmsgd\.Show\s*\(                           # msgd.Show(
    )
    [^"\n]*?                                           # cualquier args previos
    "([^"\n]+)"                                        # captura el primer string literal no vacío
    """,
    re.VERBOSE,
)

_RE_RIDIOMA_USAGE = re.compile(r"\bIdm\.Texto\s*\(|\bcoMens\.m\d+\b")
_RE_TECHNICAL_LOOKING = re.compile(
    r"^[A-Z_][A-Z0-9_]*$"          # CONSTANTE
    r"|^@p_\w+$|^:p_\w+$"          # parámetro SQL
    r"|^[a-zA-Z]+\.\w+$"           # rutas estilo Foo.Bar
)


def _check_r1_ridioma(hunks: list[Hunk]) -> list[Finding]:
    findings: list[Finding] = []
    for hunk in hunks:
        if not hunk.file.endswith(CS_EXTENSIONS):
            continue
        for i, added in enumerate(hunk.added):
            content = added.content
            # Si la línea ya usa Idm.Texto / coMens, asumimos OK
            if _RE_RIDIOMA_USAGE.search(content):
                continue
            m = _RE_USER_VISIBLE_LITERAL.search(content)
            if not m:
                continue
            literal = m.group(1)
            if not literal.strip():
                continue
            # Si parece técnico (toda mayúscula, nombre de parámetro, etc.), saltar
            if _RE_TECHNICAL_LOOKING.match(literal):
                continue
            prev = hunk.added[i - 1].content if i > 0 else ""
            if _is_disabled("R1", content, prev):
                continue
            findings.append(Finding(
                rule_id="R1",
                severity=Severity.BLOQUEANTE,
                file=hunk.file,
                line=added.line_no,
                snippet=content.strip(),
                fix_hint=f"Reemplazar el string literal por "
                         f"`Idm.Texto(coMens.mXXXX, \"{literal[:40]}...\")`. "
                         f"Crear la entrada RIDIOMA si no existe.",
                anchor="core_rules.md#r1-ridioma",
            ))
    return findings


# ── R10 — Verificación post-query ────────────────────────────────────────────

# Detectar `EjecutarQuery(...)` o `EjecutarNonQuery(...)` que NO esté seguido
# (en las próximas N líneas dentro del hunk o context_after) por una verificación
# de errores: `if (conn.Errores.Cantidad() != 0)`, `if (this.Errores.Cantidad() != 0)`
# o equivalente.

_RE_EJECUTAR_QUERY = re.compile(r"\b(?:EjecutarQuery|EjecutarNonQuery|EjecutarStoredProcedure)\s*\(")
_RE_VERIFICACION_ERRORES = re.compile(
    r"\b(?:conn|this)\.Errores\.Cantidad\s*\(\s*\)\s*!=\s*0"
)
# Cuántas líneas mirar adelante para encontrar la verificación
_R10_LOOKAHEAD = 5


def _check_r10_post_query(hunks: list[Hunk]) -> list[Finding]:
    findings: list[Finding] = []
    for hunk in hunks:
        if not hunk.file.endswith(CS_EXTENSIONS):
            continue
        # Construir lista combinada: added + context_after (para mirar más allá del hunk)
        all_lines = [a.content for a in hunk.added] + hunk.context_after
        added_count = len(hunk.added)
        for i, added in enumerate(hunk.added):
            content = added.content
            if not _RE_EJECUTAR_QUERY.search(content):
                continue
            # Mirar siguientes _R10_LOOKAHEAD líneas
            window = all_lines[i + 1: i + 1 + _R10_LOOKAHEAD]
            verified = any(_RE_VERIFICACION_ERRORES.search(l) for l in window)
            if verified:
                continue
            prev = hunk.added[i - 1].content if i > 0 else ""
            if _is_disabled("R10", content, prev):
                continue
            findings.append(Finding(
                rule_id="R10",
                severity=Severity.ADVERTENCIA,
                file=hunk.file,
                line=added.line_no,
                snippet=content.strip(),
                fix_hint="Después de `EjecutarQuery`, agregar: "
                         "`if (conn.Errores.Cantidad() != 0) { this.Errores = conn.Errores; return null; }`.",
                anchor="core_rules.md#r10-verificacion-post-query",
            ))
    return findings


# ── Helpers de path ──────────────────────────────────────────────────────────

def _is_facade(path: str) -> bool:
    return any(p in path for p in FACADE_PATHS)


def _is_bus_or_dalc(path: str) -> bool:
    return any(p in path for p in BUS_DALC_PATHS)


def _is_batch_orchestrator(path: str) -> bool:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name in BATCH_ORCHESTRATOR_FILES or "/RSProcIN/" in path or "/Motor/" in path


# ── API pública ──────────────────────────────────────────────────────────────

_RULE_FUNCS = {
    "R1": _check_r1_ridioma,
    "R2": _check_r2_cconexion_in_facade,
    "R3": _check_r3_transactions_in_facade,
    "R4": _check_r4_sql_injection,
    "R10": _check_r10_post_query,
}


def lint_diff(diff_text: str, rules: list[str] | None = None) -> list[Finding]:
    """
    Analiza un diff y retorna los hallazgos agrupados de las reglas pedidas.

    Args:
        diff_text: salida de `git diff` (unified format con -U N).
        rules: lista de reglas a aplicar. Si None, aplica todas las disponibles.

    Returns:
        Lista de Finding ordenada por archivo y línea.
    """
    if rules is None:
        rules = list(_RULE_FUNCS.keys())
    hunks = list(parse_diff(diff_text))
    findings: list[Finding] = []
    for r in rules:
        fn = _RULE_FUNCS.get(r)
        if fn is None:
            continue
        findings.extend(fn(hunks))
    findings.sort(key=lambda f: (f.file, f.line, f.rule_id))
    return findings


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T1 Golden Rules Linter — Fase 2.")
    parser.add_argument(
        "--rules", default=",".join(_RULE_FUNCS.keys()),
        help="Lista separada por comas. Default: R1,R2,R3,R4,R10."
    )
    parser.add_argument(
        "--format", choices=("json", "human"), default="human",
        help="Formato de salida. JSON va a stdout. Human va a stderr."
    )
    parser.add_argument(
        "--diff-file", default="-",
        help="Archivo con el diff. '-' = stdin."
    )
    args = parser.parse_args(argv)

    if args.diff_file == "-":
        diff_text = sys.stdin.read()
    else:
        diff_text = Path(args.diff_file).read_text(encoding="utf-8", errors="replace")

    rules = [r.strip() for r in args.rules.split(",") if r.strip()]

    try:
        findings = lint_diff(diff_text, rules=rules)
    except Exception as e:  # noqa: BLE001
        print(f"[lint-golden-rules] error interno: {e}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps([f.to_dict() for f in findings], indent=2, ensure_ascii=False))
    else:
        _report_human(findings)

    return 1 if is_blocking(findings) else 0


def _report_human(findings: list[Finding]) -> None:
    if not findings:
        print("[lint-golden-rules] ✓ sin hallazgos.", file=sys.stderr)
        return
    blockers = [f for f in findings if f.severity == Severity.BLOQUEANTE]
    advisories = [f for f in findings if f.severity != Severity.BLOQUEANTE]
    print("", file=sys.stderr)
    print(f"═══ T1 GOLDEN RULES LINTER — {len(findings)} hallazgo(s) ═══", file=sys.stderr)
    if blockers:
        print(f"  BLOQUEANTES: {len(blockers)}", file=sys.stderr)
        for f in blockers:
            print(f"    ✗ [{f.rule_id}] {f.file}:{f.line}", file=sys.stderr)
            print(f"        {f.snippet[:120]}", file=sys.stderr)
            print(f"        → {f.fix_hint}", file=sys.stderr)
            print(f"        ref: {f.anchor}", file=sys.stderr)
    if advisories:
        print(f"  ADVISORIES: {len(advisories)}", file=sys.stderr)
        for f in advisories:
            print(f"    ! [{f.rule_id}] {f.file}:{f.line} — {f.snippet[:80]}", file=sys.stderr)
    print("", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
