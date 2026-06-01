"""
services/db_query.py — Ejecución server-side de SELECTs read-only para los
agentes técnicos. Plan: §4.4 / §7.1 de 16_PLAN_GENERALIZACION_AGENTES_MULTI_CLIENTE.md.

Política de seguridad (defensa en profundidad):
  1. SOLO SELECT (y WITH ... SELECT). Cualquier otro statement → rechazo.
  2. Comentarios `--` y `/* */` se strippean ANTES de validar el statement.
  3. Multi-statement (más de un `;` con contenido) → rechazo.
  4. La credencial vive cifrada en `auth/db_readonly.json` (DPAPI); nunca se
     loguea ni se devuelve.
  5. Cada ejecución queda en `data/db_query_audit.jsonl` con
     ticket_id, query (sanitizada), duration_ms, row_count, actor.

NOTA: este módulo NO ejecuta la query contra la BD real (no es responsabilidad
del scope del plan multi-cliente). El runner real se enchufa más adelante; hoy
el endpoint:
  - Valida la query.
  - Resuelve la credencial.
  - Loguea el evento.
  - Devuelve `{ok, would_execute, dialect}` para que el agente avance con
    el contrato pero el resultado real lo provea el operador (mismo patrón que
    el dml_policy "prohibited_runtime_must_emit_sql": Stacky emite el SQL,
    el operador lo ejecuta).

Esto mantiene la fase 1 reversible: no añadimos dependencias de drivers de BD
todavía. Cuando el operador quiera pasar al modo "ejecutar de verdad", se
cambia `execute_query()` para conectarse al server según `database.type`.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime_paths import data_dir
from services.client_profile import load_client_profile
from services.secrets_store import read_secret_from_file


_AUDIT_FILENAME = "db_query_audit.jsonl"
_MAX_QUERY_BYTES = 64 * 1024  # 64 KB
_DEFAULT_TIMEOUT_S = 30
_DEFAULT_ROW_LIMIT = 1000

# Statements que el sanitizer DEBE bloquear (mayúsculas/minúsculas indistintas).
_FORBIDDEN_LEADING_KEYWORDS: frozenset[str] = frozenset({
    "insert", "update", "delete", "merge", "drop", "alter", "create",
    "truncate", "grant", "revoke", "exec", "execute", "call", "do",
    "shutdown", "kill", "lock", "rename", "comment", "use",
})

# Statements permitidos: solo SELECT puro o CTE con SELECT.
_ALLOWED_LEADING_KEYWORDS: frozenset[str] = frozenset({"select", "with"})

# Comentarios estilo SQL.
_SINGLE_LINE_COMMENT = re.compile(r"--[^\n\r]*")
_MULTI_LINE_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


class DbQueryError(RuntimeError):
    """Error de validación / ejecución de query SELECT."""


@dataclass
class QueryValidation:
    ok: bool
    statement_kind: str = ""
    sanitized: str = ""
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "statement_kind": self.statement_kind,
            "errors": list(self.errors),
        }


def _strip_comments(sql: str) -> str:
    """Elimina comentarios SQL respetando strings sería más robusto, pero el
    universo de queries que un analista técnico tipea es simple. Si en el
    futuro se permite SQL más complejo, conviene parsearlo con sqlparse."""
    no_block = _MULTI_LINE_COMMENT.sub(" ", sql)
    no_line = _SINGLE_LINE_COMMENT.sub(" ", no_block)
    return no_line


def validate_select_only(sql: Any) -> QueryValidation:
    """Devuelve un resultado de validación. No lanza."""
    if not isinstance(sql, str) or not sql.strip():
        return QueryValidation(ok=False, errors=["query vacía"])
    if len(sql.encode("utf-8")) > _MAX_QUERY_BYTES:
        return QueryValidation(
            ok=False,
            errors=[f"query excede {_MAX_QUERY_BYTES} bytes"],
        )

    sanitized = _strip_comments(sql).strip()
    if not sanitized:
        return QueryValidation(ok=False, errors=["query solo contiene comentarios"])

    # Trim trailing `;` y rechazar si hay múltiples statements con contenido.
    parts = [p.strip() for p in sanitized.split(";") if p.strip()]
    if len(parts) > 1:
        return QueryValidation(
            ok=False,
            errors=["multi-statement no permitido (separar con ';' adicional rechazado)"],
        )
    if not parts:
        return QueryValidation(ok=False, errors=["query vacía tras strip"])

    head = parts[0]
    first_token = head.split(None, 1)[0].lower().lstrip("(")
    if first_token in _FORBIDDEN_LEADING_KEYWORDS:
        return QueryValidation(
            ok=False,
            statement_kind=first_token,
            errors=[
                f"DML/DDL prohibido: la query empieza con '{first_token}'. Solo SELECT (o WITH ... SELECT) está permitido."
            ],
        )
    if first_token not in _ALLOWED_LEADING_KEYWORDS:
        return QueryValidation(
            ok=False,
            statement_kind=first_token,
            errors=[
                f"Statement '{first_token}' no permitido. Solo SELECT (o WITH ... SELECT)."
            ],
        )

    # Heurístico anti-INSERT/UPDATE en CTE: si arranca con WITH, exigir que
    # contenga 'select' y no contenga keywords mutantes fuera de strings.
    if first_token == "with":
        lowered = head.lower()
        if " select " not in f" {lowered} ":
            return QueryValidation(
                ok=False,
                statement_kind="with",
                errors=["WITH sin SELECT final no permitido"],
            )
        for bad in ("insert ", "update ", "delete ", "merge ", "drop ", "alter "):
            if bad in lowered:
                return QueryValidation(
                    ok=False,
                    statement_kind="with",
                    errors=[f"WITH contiene operación mutante '{bad.strip()}'"],
                )

    return QueryValidation(ok=True, statement_kind=first_token, sanitized=head)


def _audit_path() -> Path:
    return data_dir() / _AUDIT_FILENAME


def record_audit_event(
    *,
    ticket_id: int | str | None,
    project: str,
    query: str,
    duration_ms: int,
    row_count: int,
    result: str,
    actor: str = "operator",
    detail: dict | None = None,
) -> dict:
    event = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "ticket_id": ticket_id,
        "project": project,
        "actor": actor,
        "result": result,
        "duration_ms": duration_ms,
        "row_count": row_count,
        "query": query[:8192],  # nunca loggear más de 8KB para no inflar el jsonl
        "detail": detail or {},
    }
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def _resolve_db_readonly(project_name: str) -> dict:
    """Devuelve { 'server', 'database', 'user', 'password', 'auth_file' } o {} si no hay credencial."""
    from project_manager import PROJECTS_DIR

    profile = load_client_profile(project_name) or {}
    db = profile.get("database") or {}
    auth_ref = (db.get("readonly_auth_ref") or "auth/db_readonly.json").strip()
    auth_path = PROJECTS_DIR / project_name.upper() / auth_ref
    if not auth_path.exists():
        return {}
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    password_secret = read_secret_from_file(
        auth_path, "password", format_field="password_format"
    )
    if not password_secret.value:
        return {}
    return {
        "server":   payload.get("server") or db.get("server") or "",
        "database": payload.get("database") or "",
        "user":     payload.get("user") or db.get("readonly_user_hint") or "",
        "password": password_secret.value,
        "auth_file": auth_ref,
        "dialect":  db.get("type") or "",
    }


def execute_query(
    *,
    project: str,
    ticket_id: int | str | None,
    sql: str,
    actor: str = "operator",
    row_limit: int = _DEFAULT_ROW_LIMIT,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
    detail: dict | None = None,
) -> dict:
    """Valida + (en el futuro) ejecuta + audita.

    HOY: NO conecta a la BD. Devuelve `would_execute=True` y un mensaje
    indicando que el operador debe ejecutar el SQL emitido (consistente con
    `dml_policy = prohibited_runtime_must_emit_sql`).

    Cuando se enchufe el driver real (sqlalchemy/pyodbc/psycopg/pymysql según
    `database.type`), la función:
      - Conectará usando `_resolve_db_readonly(project)`.
      - Forzará un statement timeout de `timeout_s`.
      - Limitará a `row_limit`.
      - Retornará `{rows, columns, row_count, duration_ms}`.
    """
    started_at = time.monotonic()
    validation = validate_select_only(sql)
    if not validation.ok:
        record_audit_event(
            ticket_id=ticket_id,
            project=project,
            query=sql if isinstance(sql, str) else str(sql),
            duration_ms=int((time.monotonic() - started_at) * 1000),
            row_count=0,
            result="rejected",
            actor=actor,
            detail={"errors": validation.errors, "kind": validation.statement_kind},
        )
        raise DbQueryError("; ".join(validation.errors))

    db_auth = _resolve_db_readonly(project)
    if not db_auth:
        record_audit_event(
            ticket_id=ticket_id,
            project=project,
            query=validation.sanitized,
            duration_ms=int((time.monotonic() - started_at) * 1000),
            row_count=0,
            result="missing_credentials",
            actor=actor,
            detail={"kind": validation.statement_kind},
        )
        raise DbQueryError(
            "BD readonly no configurada: guardá la credencial vía POST /api/projects/<name>/db-readonly-auth."
        )

    # Stub: en el futuro, conectar y ejecutar. Por ahora dejamos el contrato listo.
    duration_ms = int((time.monotonic() - started_at) * 1000)
    record_audit_event(
        ticket_id=ticket_id,
        project=project,
        query=validation.sanitized,
        duration_ms=duration_ms,
        row_count=0,
        result="would_execute",
        actor=actor,
        detail={
            "kind": validation.statement_kind,
            "dialect": db_auth.get("dialect") or "",
            "row_limit": row_limit,
            "timeout_s": timeout_s,
            "user": db_auth.get("user") or "",
            "server": db_auth.get("server") or "",
            **(detail or {}),
        },
    )

    return {
        "ok": True,
        "would_execute": True,
        "statement_kind": validation.statement_kind,
        "sanitized_query": validation.sanitized,
        "dialect": db_auth.get("dialect") or "",
        "server": db_auth.get("server") or "",
        "user": db_auth.get("user") or "",
        "row_limit": row_limit,
        "timeout_s": timeout_s,
        "duration_ms": duration_ms,
        "note": (
            "Stub fase 1: la query fue validada y auditada, pero NO se ejecutó "
            "contra la BD. Stacky emite el SQL para que el operador lo ejecute, "
            "siguiendo dml_policy='prohibited_runtime_must_emit_sql'."
        ),
    }


def list_audit_events(
    *,
    ticket_id: int | str | None = None,
    project: str | None = None,
    limit: int = 100,
) -> list[dict]:
    path = _audit_path()
    if not path.exists():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ticket_id is not None and str(ev.get("ticket_id")) != str(ticket_id):
            continue
        if project and str(ev.get("project") or "").upper() != str(project).upper():
            continue
        events.append(ev)
    events.reverse()
    return events[: max(1, min(limit, 1000))]


__all__ = [
    "DbQueryError",
    "QueryValidation",
    "execute_query",
    "list_audit_events",
    "record_audit_event",
    "validate_select_only",
]
