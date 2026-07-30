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

    # Estados que significan "a este ticket le FALTAN operaciones". La
    # rehidratación NO debe pisarlos con `done`: encontrar el issue en GitLab
    # prueba que el ISSUE existe, no que sus notas/adjuntos se hayan migrado.
    #
    # Sin esta salvaguarda, reanudar una corrida cortada deja HUECOS silenciosos:
    # la corrida 1 crea el issue y falla una nota (ticket -> `partial`); al
    # reanudar, la rehidratación lo sube a `done`, y entonces `plan_migration`
    # (`migrator_mg_core.py:304-306`) saltea el ticket COMPLETO — las notas que
    # faltaban no se re-planifican nunca y nada avisa.
    _PENDIENTES = {"partial", "failed", "pending"}
    estados_previos = {
        row["mantis_issue_id"]: row["status"]
        for row in get_full_mapping(conn, project_path)
    }

    for item in writer.fetch_open_items():
        description = item.get("description") or item.get("description_html") or ""
        match = marker_re.search(description)
        if not match:
            continue

        mantis_issue_id = match.group(1)
        gitlab_iid = str(item.get("iid") or item.get("id") or "")
        previo = estados_previos.get(mantis_issue_id)
        # Se conserva el estado pendiente; el `gitlab_iid` se actualiza igual,
        # porque es el dato que evita la creación duplicada en
        # `_apply_create_item`.
        nuevo_status = previo if previo in _PENDIENTES else "done"
        upsert_mapping(
            conn,
            project_path=project_path,
            mantis_project_id=mantis_project_id,
            mantis_issue_id=mantis_issue_id,
            gitlab_iid=gitlab_iid,
            status=nuevo_status,
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

    # SEGUNDA barrera de idempotencia, imprescindible para reanudar sin duplicar.
    #
    # El escenario: la corrida 1 crea el issue (queda `done`) y después una de
    # SUS notas falla — el `except` de `execute_migration` marca el ticket como
    # `partial`, no `done`. Al reanudar, `plan_migration` NO saltea los `partial`
    # (solo los `done`), así que vuelve a emitir la op `create_item`… y con el
    # chequeo de arriba como única barrera, `live_map` diría `partial` ≠ `done` y
    # se crearía un SEGUNDO issue para el mismo ticket de Mantis.
    #
    # La prueba de que el issue ya existe no es el `status` (que refleja si
    # FALTAN ops) sino el `gitlab_iid`: si hay uno mapeado, el issue está creado.
    # En ese caso se saltea la creación pero NO el resto del plan, así que las
    # notas y adjuntos que faltaban SÍ se reintentan (son idempotentes por su
    # propio marcador).
    iid_existente = get_gitlab_iid(
        conn,
        project_path=project_path,
        mantis_project_id=mantis_project_id,
        mantis_issue_id=issue_id,
    )
    if iid_existente:
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
    # `created_at` viaja en el payload del plan (ISO 8601 o None). Backdatea la
    # nota para que la timeline del issue en GitLab respete el orden real de
    # Mantis en vez de apilar las 137 notas en el minuto de la migración.
    writer.post_comment(dest_iid, full_body, created_at=(op.payload or {}).get("created_at"))
    result.applied += 1


def _apply_upload_attachment(
    op,
    writer: DestinationWriter,
    conn,
    *,
    project_path: str,
    mantis_project_id: str,
    result: MgExecutionResult,
    origin_adapter=None,
    attachment_options: "dict | None" = None,
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
    # El adapter de origen y los límites de tamaño se INYECTAN en ejecución
    # (no viajan en el plan: no son serializables / son config de corrida).
    options = attachment_options or {}
    adapter = origin_adapter if origin_adapter is not None else payload.get("origin_adapter")
    if adapter is None:
        raise RuntimeError(
            "upload_attachment: falta el origin_adapter para descargar el "
            "binario desde Mantis (se inyecta en execute_migration)."
        )
    attachment_meta = payload.get("attachment_meta", {}) or {}

    # Idempotencia (§11): `link_attachment` escribe en la DESCRIPCIÓN, así que
    # el `comment_exists` que protege a los comentarios no aplica acá. Sin
    # este chequeo, re-correr la migración vuelve a subir cada binario y
    # concatena otra vez el markdown, duplicando adjuntos en silencio.
    if writer.attachment_exists(dest_iid, op.marker, attachment_meta.get("name", "")):
        result.skipped += 1
        return

    outcome = migrator_mg_attachments.migrate_attachment_mg(
        attachment_meta,
        writer,
        adapter,
        dest_iid=dest_iid,
        max_size_mb=options.get("max_size_mb", 50),
        skip_if_over_limit=options.get("skip_if_over_limit", True),
        marker=op.marker,
    )
    if isinstance(outcome, dict) and outcome.get("skipped"):
        # Saltado por tamaño: NO cuenta como aplicado; queda declarado.
        result.skipped += 1
        return

    # `migrate_attachment_mg` NUNCA propaga: atrapa toda excepción y devuelve
    # `{"skipped": False, "verified": False, "error": ...}`. Contar eso como
    # aplicado convierte un fallo real en un éxito reportado — y eso fue
    # exactamente lo que pasó en la migración de Ripley del 2026-07-29: el
    # `REQUESTS_CA_BUNDLE` global (destination_writer.py:189) rompió el TLS
    # contra Mantis, TODA descarga de adjunto falló, y la corrida las contó
    # como "aplicadas". El reporte dio verde y no se migró ni un adjunto.
    # Se re-lanza para que el `except` del loop de `execute_migration` lo
    # registre en `result.failed` y deje el ticket en `status="partial"`,
    # que es lo que hace reintentable la corrida siguiente.
    if isinstance(outcome, dict) and outcome.get("error"):
        raise RuntimeError(
            f"upload_attachment: el adjunto {outcome.get('name')!r} del issue "
            f"Mantis {issue_id} NO se migró: {outcome['error']}"
        )
    if isinstance(outcome, dict) and not outcome.get("verified"):
        raise RuntimeError(
            f"upload_attachment: el adjunto {outcome.get('name')!r} del issue "
            f"Mantis {issue_id} no quedó verificado (outcome={outcome!r})."
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
    origin_adapter=None,
    attachment_options: "dict | None" = None,
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
                    origin_adapter=origin_adapter,
                    attachment_options=attachment_options,
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
