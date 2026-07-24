"""tools/migrar_mantis_gitlab/migrator_mg_executor.py — Plan 217 Batch 4, F5b.

Ejecución idempotente por marker + checkpoint + rehidratación PROPIA (§11
del plan). NO reusa `hydrate_map_from_destination` de
`services/migrator_executor.py:154` — esa función está acoplada a `db`
(conexión Flask compartida) y `stacky_project`, y usa el marker ADO
(`_MARKER_RE`, formato `stacky-migrated:ado:{id}`). Este módulo implementa
su propia versión, sobre el SQLite propio y portable de
`migrator_mg_map.py`, con el marker Mantis (`_MG_MARKER_TEMPLATE` de
`migrator_mg_core.py`).

Decisión de diseño (documentada, no trivial): `execute_migration` NO recibe
`existing_map` como parámetro explícito — el plan de este batch lo describe
en prosa como "parámetro, ya construido antes por
`hydrate_map_from_destination_mg`", pero la firma que el mismo batch fija
para `execute_migration` no lo incluye. Se resuelve la contradicción así:
como `hydrate_map_from_destination_mg` ya deja el mapeo PERSISTIDO en
`conn` (vía `upsert_mapping`) antes de que el caller invoque
`execute_migration`, este último simplemente lee `get_full_mapping(conn,
project_path)` al arrancar para construir su `live_map` en memoria — mismo
resultado, sin necesidad de un parámetro redundante, y consistente con "la
verdadera fuente de idempotencia es el mapeo persistido" (§11).
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from . import run_state
from .destination_writer import DestinationWriter
from .migrator_mg_core import MgMigrationPlan
from .migrator_mg_map import get_full_mapping, get_gitlab_iid, upsert_mapping

_LOGGER_NAME = "migrar_mantis_gitlab.executor"

# Op kinds que este executor sabe aplicar directamente. `create_issue_link`
# NO está acá: las relaciones son una segunda pasada aparte
# (`migrator_mg_links.migrate_relationships`, F6b) que corre DESPUÉS de que
# `execute_migration` terminó de crear todos los issues — no es parte del
# loop principal de ops del plan.
_APPLICABLE_OP_KINDS = frozenset({"create_item", "post_comment", "upload_attachment"})


@dataclass
class MgExecutionResult:
    applied: int = 0
    skipped: int = 0
    failed: list[dict] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)


def _build_marker_regex(mantis_project_id: str) -> "re.Pattern[str]":
    """Regex propia (NO la `_MARKER_RE` de `services/migrator_executor.py`,
    que es formato ADO) para el marker Mantis `<!--
    stacky-migrated:mantis:{project_id}:{issue_id} -->` (`migrator_mg_core.
    _MG_MARKER_TEMPLATE`), acotada a UN `mantis_project_id` puntual."""
    return re.compile(
        rf"<!--\s*stacky-migrated:mantis:{re.escape(str(mantis_project_id))}:(\d+)\s*-->"
    )


def hydrate_map_from_destination_mg(
    writer: DestinationWriter,
    conn,
    *,
    project_path: str,
    mantis_project_id: str,
) -> dict[str, str]:
    """Rehidratación PROPIA por marker (§11 del plan): relee TODOS los
    items del destino (`writer.fetch_open_items()`, agregado en el Paso 0
    de este batch), busca el marker Mantis en la descripción de cada uno, y
    por cada match hace `upsert_mapping(..., status="done")`. Devuelve el
    mapeo fusionado (local ∪ destino) ya persistido, reindexado
    `{mantis_issue_id: status}` — el shape que espera
    `migrator_mg_core.plan_migration(existing_map=...)`.

    Es "fuente de verdad SECUNDARIA" (§11): si el SQLite local se pierde o
    la corrida continúa en otra máquina, esto reconstruye el mapeo leyendo
    GitLab directamente, sin depender del checkpoint local."""
    marker_re = _build_marker_regex(mantis_project_id)

    for item in writer.fetch_open_items():
        description = item.get("description") or item.get("description_html") or ""
        match = marker_re.search(description)
        if not match:
            continue

        mantis_issue_id = match.group(1)
        gitlab_iid = str(item.get("iid") or item.get("id") or "")
        upsert_mapping(
            conn,
            project_path=project_path,
            mantis_project_id=mantis_project_id,
            mantis_issue_id=mantis_issue_id,
            gitlab_iid=gitlab_iid,
            status="done",
        )

    return {row["mantis_issue_id"]: row["status"] for row in get_full_mapping(conn, project_path)}


def _apply_create_item(
    op,
    writer: DestinationWriter,
    conn,
    *,
    project_path: str,
    mantis_project_id: str,
    live_map: dict[str, str],
    result: MgExecutionResult,
) -> None:
    issue_id = op.mantis_issue_id

    if live_map.get(issue_id) == "done":
        result.skipped += 1
        return

    payload = dict(op.payload)

    if op.dest_parent_mantis_id:
        parent_gitlab_iid = get_gitlab_iid(
            conn,
            project_path=project_path,
            mantis_project_id=mantis_project_id,
            mantis_issue_id=op.dest_parent_mantis_id,
        )
        if parent_gitlab_iid is None:
            # §7/§16-F5 del plan: el padre no está resuelto todavía (no
            # migrado o la topología no lo garantizó) — se crea igual, sin
            # parent, y se registra como huérfano (mismo patrón que
            # `services/migrator_executor.py:76-80` para ADO).
            result.orphaned.append(issue_id)
        else:
            payload["dest_parent_gitlab_iid"] = parent_gitlab_iid

    description = payload.get("description", "") or ""
    if op.marker not in description:
        payload["description"] = f"{description}\n\n{op.marker}" if description else op.marker

    created = writer.create_item(payload)
    gitlab_iid = str(created.get("iid") or created.get("id") or "")

    upsert_mapping(
        conn,
        project_path=project_path,
        mantis_project_id=mantis_project_id,
        mantis_issue_id=issue_id,
        gitlab_iid=gitlab_iid,
        status="done",
    )
    live_map[issue_id] = "done"
    result.applied += 1


def _apply_post_comment(
    op,
    writer: DestinationWriter,
    conn,
    *,
    project_path: str,
    mantis_project_id: str,
    result: MgExecutionResult,
) -> None:
    issue_id = op.mantis_issue_id
    dest_iid = get_gitlab_iid(
        conn,
        project_path=project_path,
        mantis_project_id=mantis_project_id,
        mantis_issue_id=issue_id,
    )
    if dest_iid is None:
        raise RuntimeError(
            f"post_comment: issue Mantis {issue_id} todavía no tiene gitlab_iid mapeado "
            "(create_item debe aplicarse antes que sus post_comment en el orden del plan)."
        )

    if writer.comment_exists(dest_iid, op.marker):
        result.skipped += 1
        return

    body = (op.payload or {}).get("body", "")
    full_body = f"{body}\n\n{op.marker}" if op.marker not in body else body
    writer.post_comment(dest_iid, full_body)
    result.applied += 1


def _apply_upload_attachment(
    op,
    writer: DestinationWriter,
    conn,
    *,
    project_path: str,
    mantis_project_id: str,
    result: MgExecutionResult,
) -> None:
    # Import perezoso: `migrator_mg_attachments.py` (F6a, mismo batch)
    # importa `destination_writer` — evita cualquier ciclo de import y
    # mantiene el executor liviano si solo se usan create_item/post_comment.
    from . import migrator_mg_attachments

    issue_id = op.mantis_issue_id
    dest_iid = get_gitlab_iid(
        conn,
        project_path=project_path,
        mantis_project_id=mantis_project_id,
        mantis_issue_id=issue_id,
    )
    if dest_iid is None:
        raise RuntimeError(
            f"upload_attachment: issue Mantis {issue_id} todavía no tiene gitlab_iid mapeado."
        )

    payload = op.payload or {}
    migrator_mg_attachments.migrate_attachment_mg(
        payload.get("attachment_meta", {}),
        writer,
        payload.get("origin_adapter"),
        dest_iid=dest_iid,
        max_size_mb=payload.get("max_size_mb", 50),
        skip_if_over_limit=payload.get("skip_if_over_limit", True),
    )
    result.applied += 1


def execute_migration(
    plan: MgMigrationPlan,
    writer: DestinationWriter,
    conn,
    *,
    project_path: str,
    mantis_project_id: str,
    checkpoint_path: str,
    checkpoint_every: int = 10,
    run_id: Optional[str] = None,
) -> MgExecutionResult:
    """Ejecuta el plan en orden (ya viene ordenado topológicamente por
    `plan_migration`), idempotente por marker/mapeo persistido.

    Errores por-op (§9 del plan: "no abortan la corrida completa") se
    capturan, van a `result.failed`, dejan el ticket en `status="partial"`
    (no `"done"`, para que una corrida futura lo reintente), y la corrida
    CONTINÚA con el resto de las ops."""
    run_id = run_id or f"run-{int(time.time())}"
    logger = logging.getLogger(_LOGGER_NAME)
    result = MgExecutionResult()

    # live_map arranca desde lo YA persistido (por `hydrate_map_from_destination_mg`,
    # llamado por el caller ANTES de esta función — ver docstring del módulo).
    live_map: dict[str, str] = {
        row["mantis_issue_id"]: row["status"] for row in get_full_mapping(conn, project_path)
    }

    applied_since_checkpoint = 0
    last_checkpointed_issue_id: Optional[str] = None

    for op in plan.ops:
        if op.op_kind not in _APPLICABLE_OP_KINDS:
            # p.ej. "create_issue_link": no es parte de este loop (ver
            # `_APPLICABLE_OP_KINDS`), se ignora acá sin marcarlo como error.
            continue

        try:
            if op.op_kind == "create_item":
                before = result.applied
                _apply_create_item(
                    op, writer, conn,
                    project_path=project_path,
                    mantis_project_id=mantis_project_id,
                    live_map=live_map,
                    result=result,
                )
                applied_this_op = result.applied > before
            elif op.op_kind == "post_comment":
                before = result.applied
                _apply_post_comment(
                    op, writer, conn,
                    project_path=project_path,
                    mantis_project_id=mantis_project_id,
                    result=result,
                )
                applied_this_op = result.applied > before
            else:  # upload_attachment
                before = result.applied
                _apply_upload_attachment(
                    op, writer, conn,
                    project_path=project_path,
                    mantis_project_id=mantis_project_id,
                    result=result,
                )
                applied_this_op = result.applied > before
        except Exception as exc:
            logger.warning(
                "execute_migration: op %s del issue %s falló, continuando (%s)",
                op.op_kind, op.mantis_issue_id, exc,
            )
            result.failed.append({
                "mantis_issue_id": op.mantis_issue_id,
                "op_kind": op.op_kind,
                "error": str(exc),
            })
            upsert_mapping(
                conn,
                project_path=project_path,
                mantis_project_id=mantis_project_id,
                mantis_issue_id=op.mantis_issue_id,
                gitlab_iid=get_gitlab_iid(
                    conn,
                    project_path=project_path,
                    mantis_project_id=mantis_project_id,
                    mantis_issue_id=op.mantis_issue_id,
                ),
                status="partial",
            )
            continue

        if applied_this_op:
            applied_since_checkpoint += 1
            last_checkpointed_issue_id = op.mantis_issue_id
            if applied_since_checkpoint >= checkpoint_every:
                run_state.save_checkpoint(
                    checkpoint_path,
                    last_mantis_issue_id=last_checkpointed_issue_id,
                    run_id=run_id,
                )
                applied_since_checkpoint = 0

    return result


def resume_migration(
    plan: MgMigrationPlan,
    writer: DestinationWriter,
    conn,
    *,
    project_path: str,
    mantis_project_id: str,
    checkpoint_path: str,
    checkpoint_every: int = 10,
) -> MgExecutionResult:
    """Wrapper delgado sobre `execute_migration` (§11 del plan).

    Decisión de diseño explícita: el checkpoint (`run_state.load_checkpoint`)
    es solo un HINT informativo — se lee y se loguea, pero NO se usa para
    filtrar/recortar el plan. La garantía real de no-duplicado la da
    `execute_migration` vía `live_map`/`status="done"` leído del mapeo
    persistido (`mantis_gitlab_map`), no este checkpoint. Filtrar el plan
    "por checkpoint" sería una optimización frágil (¿y si el checkpoint
    quedó a mitad de un ticket que falló parcialmente?) e innecesaria:
    recorrer el plan completo saltando los `done` ya es barato (O(ops), sin
    I/O de red por los saltados)."""
    logger = logging.getLogger(_LOGGER_NAME)
    checkpoint = run_state.load_checkpoint(checkpoint_path)
    if checkpoint:
        logger.info(
            "resume_migration: checkpoint encontrado (last_mantis_issue_id=%s, run_id=%s) — "
            "es solo informativo, el filtrado real de ops ya-aplicadas lo hace "
            "execute_migration vía el mapeo persistido.",
            checkpoint.get("last_mantis_issue_id"),
            checkpoint.get("run_id"),
        )

    return execute_migration(
        plan,
        writer,
        conn,
        project_path=project_path,
        mantis_project_id=mantis_project_id,
        checkpoint_path=checkpoint_path,
        checkpoint_every=checkpoint_every,
    )


__all__ = [
    "MgExecutionResult",
    "execute_migration",
    "hydrate_map_from_destination_mg",
    "resume_migration",
]
