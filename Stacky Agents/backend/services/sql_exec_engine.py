"""Plan 200 R3 — Ejecutar un script SQL contra un ambiente elegido.

Es la capacidad más peligrosa del producto: la única que ESCRIBE en una base del
operador. Toda la doctrina de la serie 122-126 es "Stacky genera, el operador
ejecuta"; esto la mueve un paso, y por eso viene con cuatro candados en serie:

1. `STACKY_SQL_EXEC_ENABLED` **default OFF** (excepción dura 2: destructiva e
   irreversible; excepción 3: necesita credenciales que no existen en una
   instalación limpia). Con la flag apagada la feature no existe: 404.
2. `exec_allowed` **por ambiente**. Registrar un ambiente para COMPARARLO
   (lectura) no habilita ESCRIBIRLE: son dos opt-in distintos, a propósito.
3. HITL por corrida: `confirm=True` + el fingerprint del texto exacto que el
   operador vio. Si el `.sql` cambió en el disco desde el preview, no se ejecuta.
4. Idempotencia: el mismo script no se aplica dos veces en el mismo ambiente sin
   un `force` explícito.

Nada de esto se dispara solo. No hay camino automático a esta función.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field

# DDL: en Oracle/MySQL auto-commitea, así que el rollback NO devuelve todo. Se
# avisa en el dry-run en vez de prometer una atomicidad que no existe.
_DDL_RE = re.compile(r"\b(CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE)\b", re.IGNORECASE)


@dataclass
class ExecResult:
    ok: bool
    dry_run: bool
    statement_count: int
    rows_affected: int | None
    error: str | None
    duration_ms: int
    statements: list = field(default_factory=list)
    partial_effects_possible: bool = False
    ledger_write_failed: bool = False


def script_fingerprint(sql_text: str) -> str:
    """sha256 del texto EXACTO: el HITL exige que coincida con lo que se mostró."""
    return hashlib.sha256((sql_text or "").encode("utf-8")).hexdigest()


def _split_statements(sql_text: str) -> list[str]:
    """Split determinista por `;` de nivel superior.

    Ignora los `;` dentro de literales y de comentarios (`--` y `/* */`), que es
    donde un split ingenuo parte un statement al medio y ejecuta basura.

    LIMITACIÓN CONOCIDA: no parsea PL/SQL. Un bloque `BEGIN … END;` con `;`
    internos se parte mal — para eso está `split_statements=False`, que manda el
    texto entero como un solo statement.
    """
    partes: list[str] = []
    actual: list[str] = []
    i = 0
    n = len(sql_text or "")
    comilla: str | None = None
    en_linea = False
    en_bloque = False

    while i < n:
        c = sql_text[i]
        siguiente = sql_text[i + 1] if i + 1 < n else ""

        if en_linea:
            actual.append(c)
            if c == "\n":
                en_linea = False
            i += 1
            continue
        if en_bloque:
            actual.append(c)
            if c == "*" and siguiente == "/":
                actual.append(siguiente)
                i += 2
                en_bloque = False
                continue
            i += 1
            continue
        if comilla is not None:
            actual.append(c)
            if c == comilla:
                # '' escapa una comilla dentro del literal.
                if siguiente == comilla:
                    actual.append(siguiente)
                    i += 2
                    continue
                comilla = None
            i += 1
            continue

        if c == "-" and siguiente == "-":
            en_linea = True
            actual.append(c)
            i += 1
            continue
        if c == "/" and siguiente == "*":
            en_bloque = True
            actual.append(c)
            actual.append(siguiente)
            i += 2
            continue
        if c in ("'", '"'):
            comilla = c
            actual.append(c)
            i += 1
            continue
        if c == ";":
            trozo = "".join(actual).strip()
            if trozo:
                partes.append(trozo)
            actual = []
            i += 1
            continue

        actual.append(c)
        i += 1

    ultimo = "".join(actual).strip()
    if ultimo:
        partes.append(ultimo)
    return partes


def execute_script(
    *,
    alias: str,
    sql_text: str,
    dry_run: bool,
    ticket_ref: str | None,
    incident_id: str | None,
    confirm_fingerprint: str,
    executed_by: str,
    split_statements: bool = True,
    force: bool = False,
) -> ExecResult:
    """Ejecuta un script YA RESUELTO server-side (la ruta lo re-lee por referencia)."""
    from config import config as _cfg

    if not getattr(_cfg, "STACKY_SQL_EXEC_ENABLED", False):
        raise PermissionError("sql_exec_disabled")

    from services import dbcompare_registry

    if not dbcompare_registry.exec_allowed(alias):
        raise PermissionError("env_not_exec_allowed")

    sha = script_fingerprint(sql_text)
    if confirm_fingerprint != sha:
        raise ValueError("fingerprint_mismatch")

    statements = _split_statements(sql_text) if split_statements else [sql_text]

    # El dry-run SIEMPRE está disponible y NUNCA muta: sale antes de la
    # idempotencia para poder previsualizar incluso un script ya aplicado.
    if dry_run:
        return ExecResult(
            ok=True, dry_run=True, statement_count=len(statements),
            rows_affected=None, error=None, duration_ms=0, statements=statements,
            partial_effects_possible=bool(_DDL_RE.search(sql_text or "")),
        )

    from services import sql_exec_ledger

    previo = sql_exec_ledger.find_executed(alias, sha)
    if previo is not None and not force:
        raise RuntimeError("already_executed")

    from services import dbcompare_engine

    cred = dbcompare_registry.get_credential(alias)
    password = (cred or {}).get("password") or ""
    engine = dbcompare_engine.open_engine(alias)
    empezado = time.monotonic()
    total_filas = 0
    try:
        # begin() commitea al salir bien y hace rollback si algo lanza. Vale para
        # DML y para DDL transaccional (SQLite/Postgres); en Oracle/MySQL el DDL
        # ya se auto-commiteó y no hay vuelta atrás — por eso el aviso del dry-run.
        with engine.begin() as conn:
            from sqlalchemy import text as _sql_text

            for stmt in statements:
                res = conn.execute(_sql_text(stmt))
                filas = getattr(res, "rowcount", None)
                total_filas += filas if filas is not None and filas >= 0 else 0
        duracion = int((time.monotonic() - empezado) * 1000)
        resultado = ExecResult(
            ok=True, dry_run=False, statement_count=len(statements),
            rows_affected=total_filas, error=None, duration_ms=duracion,
        )
    except Exception as exc:  # noqa: BLE001 — cualquier fallo del motor termina en error, no en 500
        duracion = int((time.monotonic() - empezado) * 1000)
        # El password puede venir dentro del mensaje del driver: nunca sale crudo.
        msg = dbcompare_engine._scrub(str(exc), password) if password else str(exc)
        resultado = ExecResult(
            ok=False, dry_run=False, statement_count=len(statements),
            rows_affected=None, error=msg[:1000], duration_ms=duracion,
        )
    finally:
        engine.dispose()

    # El efecto en la base YA ocurrió: que falle la bitácora no puede tumbar el
    # request. Pero tampoco puede quedar mudo — sin el aviso, el operador
    # re-ejecutaría a ciegas creyendo que no pasó nada.
    try:
        sql_exec_ledger.append_exec({
            "alias": alias,
            "engine": (cred or {}).get("engine"),
            "ticket_ref": ticket_ref,
            "incident_id": incident_id,
            "script_sha256": sha,
            "statement_count": len(statements),
            "dry_run": False,
            "result_ok": resultado.ok,
            "rows_affected": resultado.rows_affected,
            "error": resultado.error,
            "duration_ms": resultado.duration_ms,
            "executed_by": executed_by,
        })
    except Exception:  # noqa: BLE001
        resultado.ledger_write_failed = True

    return resultado
