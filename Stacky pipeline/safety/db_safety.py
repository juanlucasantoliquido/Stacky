"""
db_safety — Parser SQL + allowlist de verbos para protección de BD.

Rechaza cualquier sentencia que no sea SELECT (o WITH...SELECT) antes de que
llegue a la base de datos. Reemplaza la disciplina del LLM con un control físico
determinístico.

Uso:
    from safety.db_safety import is_safe_sql, SqlSafetyDecision

    decision = is_safe_sql("SELECT * FROM RCLIE WHERE CLEMPRESA = '01'")
    assert decision.allowed is True
    assert decision.verb == "SELECT"

    decision = is_safe_sql("UPDATE RCLIE SET CLNOMBRE = 'X'")
    assert decision.allowed is False
    assert "DML prohibido" in decision.reason
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple


# ── Constantes ────────────────────────────────────────────────────────────────

# Verbos que se rechazan siempre (a menos que force_allow_dml=True con auditoría)
_DML_VERBS: frozenset[str] = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "TRUNCATE",
        "DROP",
        "ALTER",
        "CREATE",
        "EXEC",
        "EXECUTE",
        "GRANT",
        "REVOKE",
        "DENY",
    }
)

# Allowlist default
_DEFAULT_ALLOWED: Tuple[str, ...] = ("SELECT", "WITH")

# Regex para limpiar comentarios de línea y bloque
_RE_LINE_COMMENT = re.compile(r"--[^\n]*")
_RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# Regex para separar múltiples sentencias por ;
_RE_STMT_SEP = re.compile(r";")

# Primer keyword significativo (no espacios ni saltos)
_RE_FIRST_KEYWORD = re.compile(r"\b([A-Za-z_][A-Za-z_0-9]*)\b")


# ── Dataclass de resultado ────────────────────────────────────────────────────


@dataclass
class SqlSafetyDecision:
    """Resultado de la evaluación de seguridad de una sentencia SQL."""

    allowed: bool
    verb: Optional[str]
    reason: str
    normalized_sql: str
    statements: list[str] = field(default_factory=list)


# ── Helpers internos ──────────────────────────────────────────────────────────


def _strip_comments(sql: str) -> str:
    """Elimina comentarios de bloque y de línea del SQL."""
    sql = _RE_BLOCK_COMMENT.sub(" ", sql)
    sql = _RE_LINE_COMMENT.sub(" ", sql)
    return sql


def _extract_verb(stmt: str) -> Optional[str]:
    """Devuelve el primer keyword no-whitespace en mayúsculas."""
    stmt = stmt.strip()
    m = _RE_FIRST_KEYWORD.search(stmt)
    if m:
        return m.group(1).upper()
    return None


def _split_statements(normalized: str) -> list[str]:
    """Divide por ; y filtra fragmentos vacíos."""
    stmts = [s.strip() for s in _RE_STMT_SEP.split(normalized)]
    return [s for s in stmts if s]


# ── API pública ───────────────────────────────────────────────────────────────


def is_safe_sql(
    sql: str,
    allowed: Sequence[str] = _DEFAULT_ALLOWED,
    force_allow_dml: bool = False,
    actor: Optional[str] = None,
) -> SqlSafetyDecision:
    """
    Evalúa si una sentencia SQL es segura para ejecutar contra la BD.

    Parámetros
    ----------
    sql:
        Sentencia o batch SQL a evaluar.
    allowed:
        Verbos permitidos (default: SELECT, WITH).
    force_allow_dml:
        Solo para agentes autorizados. Permite DML pero registra auditoría
        via action_log. Requiere ``actor`` no vacío.
    actor:
        Nombre del agente/usuario que solicita el override. Requerido si
        ``force_allow_dml=True``.

    Devuelve
    --------
    SqlSafetyDecision con:
        - ``allowed``: True si la sentencia pasa el filtro.
        - ``verb``: Verbo detectado (puede ser None si el SQL está vacío).
        - ``reason``: Descripción del resultado.
        - ``normalized_sql``: SQL sin comentarios.
        - ``statements``: Lista de sentencias individuales detectadas.
    """
    if not sql or not sql.strip():
        return SqlSafetyDecision(
            allowed=False,
            verb=None,
            reason="SQL vacío o solo espacios",
            normalized_sql="",
            statements=[],
        )

    normalized = _strip_comments(sql)
    statements = _split_statements(normalized)

    allowed_upper = {v.upper() for v in allowed}

    # Evaluar cada sentencia del batch
    for stmt in statements:
        verb = _extract_verb(stmt)
        if verb is None:
            continue  # sentencia vacía tras strip, ignorar

        if verb in _DML_VERBS:
            if force_allow_dml:
                if not actor:
                    return SqlSafetyDecision(
                        allowed=False,
                        verb=verb,
                        reason="force_allow_dml=True requiere actor no vacío para auditoría",
                        normalized_sql=normalized,
                        statements=statements,
                    )
                # Registrar auditoría via action_log si está disponible
                _audit_force_allow(sql=sql, verb=verb, actor=actor)
                continue  # verbo DML permitido explícitamente
            else:
                return SqlSafetyDecision(
                    allowed=False,
                    verb=verb,
                    reason=(
                        f"DML prohibido sin override explícito: verbo '{verb}' "
                        f"no está en la allowlist {sorted(allowed_upper)}"
                    ),
                    normalized_sql=normalized,
                    statements=statements,
                )

        if verb not in allowed_upper and verb not in _DML_VERBS:
            # Verbo desconocido — rechazar por precaución
            return SqlSafetyDecision(
                allowed=False,
                verb=verb,
                reason=(
                    f"Verbo '{verb}' desconocido — rechazado por precaución. "
                    f"Allowlist: {sorted(allowed_upper)}"
                ),
                normalized_sql=normalized,
                statements=statements,
            )

    # Todos los statements pasaron
    first_verb = _extract_verb(statements[0]) if statements else None
    return SqlSafetyDecision(
        allowed=True,
        verb=first_verb,
        reason="OK",
        normalized_sql=normalized,
        statements=statements,
    )


def _audit_force_allow(sql: str, verb: str, actor: str) -> None:
    """
    Registra un override DML via action_log si el módulo está disponible.
    Si action_log no está importable (ej: en tests unitarios aislados), no falla.
    """
    try:
        from action_log import log_action  # type: ignore

        log_action(
            actor=actor,
            tool="safety.db_safety.force_allow_dml",
            params={"sql_preview": sql[:200], "verb": verb},
            result={"allowed": True, "override": True},
            reverse=None,
            ticket_id=None,
        )
    except Exception:  # noqa: BLE001
        # No propagar errores del logger — la seguridad no debe depender del log
        pass
