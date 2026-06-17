"""V1.1 — Registro/versionado de prompts de agente (.agent.md).

Los .agent.md están gitignored ⇒ la DB es el único lugar posible para
historizar qué versión de prompt corrió cada run. Este servicio es el
dueño único de la tabla ``agent_prompt_versions``.

Contrato:
- record_version(filename, body, source) -> dict|None  (INSERT OR IGNORE por sha)
- ensure_version(filename, body) -> sha  (sello en el run; source="fs_scan")
- list_versions(filename) -> list[dict]
- diff_versions(from_id, to_id) -> str (unified diff)

Default OFF: nada de esto altera flujos si la tabla está vacía (retro-compat).
"""
from __future__ import annotations

import difflib
import hashlib
import logging

logger = logging.getLogger("stacky.services.agent_prompt_registry")


def compute_sha(body: str) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def record_version(filename: str, body: str, *, source: str) -> dict | None:
    """Registra una versión del prompt. Idempotente por (filename, sha256).

    Returns el dict de la versión (existente o recién creada), o None si el
    body es vacío (no se historizan prompts vacíos).
    """
    if not body:
        return None
    from db import session_scope
    from models import AgentPromptVersion

    sha = compute_sha(body)
    with session_scope() as session:
        existing = (
            session.query(AgentPromptVersion)
            .filter_by(filename=filename, sha256=sha)
            .one_or_none()
        )
        if existing is not None:
            return existing.to_dict()
        row = AgentPromptVersion(
            filename=filename, sha256=sha, body=body, source=source,
        )
        session.add(row)
        session.flush()
        return row.to_dict()


def ensure_version(filename: str, body: str) -> str | None:
    """Sello en el run: garantiza que la versión esté registrada.

    Si el archivo fue editado a mano (no entró por el import endpoint) se
    registra con source="fs_scan" para que el historial nunca tenga huecos.
    Devuelve el sha256 (o None si body vacío).
    """
    if not body:
        return None
    record_version(filename, body, source="fs_scan")
    return compute_sha(body)


def list_versions(filename: str) -> list[dict]:
    from db import session_scope
    from models import AgentPromptVersion

    with session_scope() as session:
        rows = (
            session.query(AgentPromptVersion)
            .filter_by(filename=filename)
            .order_by(AgentPromptVersion.imported_at.asc(), AgentPromptVersion.id.asc())
            .all()
        )
        return [r.to_dict() for r in rows]


def get_body(version_id: int) -> str | None:
    from db import session_scope
    from models import AgentPromptVersion

    with session_scope() as session:
        row = session.get(AgentPromptVersion, version_id)
        return row.body if row else None


def diff_versions(from_id: int, to_id: int) -> str:
    """Unified diff entre dos versiones. Lanza ValueError si falta alguna."""
    from db import session_scope
    from models import AgentPromptVersion

    with session_scope() as session:
        a = session.get(AgentPromptVersion, from_id)
        b = session.get(AgentPromptVersion, to_id)
        if a is None:
            raise ValueError(f"versión {from_id} no existe")
        if b is None:
            raise ValueError(f"versión {to_id} no existe")
        diff = difflib.unified_diff(
            (a.body or "").splitlines(keepends=True),
            (b.body or "").splitlines(keepends=True),
            fromfile=f"{a.filename}@{a.sha256[:12]}",
            tofile=f"{b.filename}@{b.sha256[:12]}",
        )
        return "".join(diff)
