"""tools/migrar_mantis_gitlab/migrator_mg_core.py — Plan 217 F4.

Generaliza el PATRÓN de `services/migrator_core.py` (plan_migration
read-only + orden topológico + snapshot con hash) para el origen Mantis.
NO edita `services/migrator_core.py` (C4 del plan): ese archivo es ADO-only
y no se toca ni se le importan símbolos escribibles.

Dos piezas de `migrator_core.py` se consideraron para reuso directo y se
descartaron a propósito (dejado documentado, no simplemente omitido):
  - `_TYPE_ORDER` (`services/migrator_core.py:14`, dict `{"Epic":0,
    "Issue":1,...}`): es ADO-específico (tipos de work item que Mantis no
    tiene). Este módulo define su PROPIO `_MG_TYPE_ORDER`, basado en el
    único criterio de jerarquía disponible en Mantis vía relaciones
    "child of": el issue tiene padre o no (2 niveles, no jerarquía
    arbitraria — el plan §7 no pide N niveles).
  - `_MARKER_TEMPLATE` (`services/migrator_core.py:24`, formato
    `stacky-migrated:ado:{ado_id}`): formato ADO. Este módulo define su
    propio `_MG_MARKER_TEMPLATE` (formato `mantis:{project_id}:{issue_id}`,
    tabla de mapeo §5 del plan, fila `id`).

Invariante READ-ONLY (mismo contrato que `migrator_core.plan_migration`):
`plan_migration()` SOLO invoca métodos `fetch_*` de `origin_adapter`. Nunca
llama nada de escritura — si el adapter pasado en un test no tuviera esos
métodos (p. ej. un fake mínimo con solo `fetch_*`), cualquier intento de
escribir explotaría por `AttributeError`. Esa ausencia ES la prueba de que
el dry-run es real, no una promesa de diseño.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Optional

from .mapping.category_map import map_category
from .mapping.date_map import extraer_fecha_nota, extraer_fechas_issue
from .mapping.custom_field_map import map_custom_fields
from .mapping.priority_severity_map import UnmappedPriorityError, map_priority, map_severity
from .mapping.status_map import map_status
from .mapping.tag_map import map_tags
from .mapping.user_map import UserMappingError, map_user
from .mapping.version_map import map_version

# Marker de idempotencia propio (§5 del plan, fila `id`; NO el de ADO).
_MG_MARKER_TEMPLATE = "<!-- stacky-migrated:mantis:{project_id}:{issue_id} -->"

# Nombres canónicos (inglés) de los status de Mantis que implican ticket cerrado.
# Coinciden con los IDs 80/90 de `services/mantis_client._STANDARD_STATUS_IDS`.
# Se usan SOLO para decidir si el bloque de metadata debe declarar la fecha de
# cierre; quién cierra la issue en GitLab es `field_mapping.status.<X>.
# gitlab_state`, que manda y es configurable por cliente.
_MG_STATUS_CERRADOS = frozenset({"resolved", "closed"})
# Markers propios de comentarios y adjuntos: la idempotencia de cada op se
# resuelve por marker (§11), así que cada nota/adjunto necesita el suyo —
# si no, re-ejecutar duplicaría comentarios en los issues ya migrados.
_MG_NOTE_MARKER_TEMPLATE = (
    "<!-- stacky-migrated:mantis-note:{project_id}:{issue_id}:{note_id} -->"
)
_MG_ATTACH_MARKER_TEMPLATE = (
    "<!-- stacky-migrated:mantis-file:{project_id}:{issue_id}:{file_id} -->"
)


def _build_comment_body(comment: dict) -> str:
    """Cuerpo de la nota en GitLab preservando la autoría original de Mantis.

    GitLab atribuye toda nota al dueño del token (salvo modo `sudo`, que
    exige PAT admin), así que el autor y la fecha reales de Mantis se
    conservan como encabezado del cuerpo (§6 del plan)."""
    reporter = str(comment.get("reporter") or "").strip()
    date = str(comment.get("date") or "").strip()
    text = str(comment.get("text") or "").strip()
    partes: list[str] = []
    if reporter or date:
        partes.append(
            "> **{}**{}".format(
                reporter or "(autor desconocido)",
                f" — {date}" if date else "",
            )
        )
    # Mantis distingue notas privadas; GitLab no tiene equivalente en las
    # notas de issue. Se marcan de forma inequívoca para que nadie las lea
    # como si hubieran sido públicas en el origen (§6: lo que se degrada
    # queda declarado, nunca en silencio).
    if comment.get("private"):
        partes.append("> 🔒 **NOTA PRIVADA en Mantis** — no era visible para todos los usuarios del origen.")
    partes.append(text)
    return "\n\n".join(p for p in partes if p)

# Orden topológico propio de Mantis — 2 niveles (sin padre / con padre),
# NO el `_TYPE_ORDER` de migrator_core.py (ver docstring del módulo).
_MG_TYPE_ORDER: dict[str, int] = {
    "no_parent": 0,
    "has_parent": 1,
}


# ── Dataclasses propias (no reusan MigrationOp/MigrationPlan de ADO) ──────


@dataclass(frozen=True)
class MgMigrationOp:
    op_kind: Literal["create_item", "post_comment", "upload_attachment", "create_issue_link"]
    mantis_issue_id: str
    dest_parent_mantis_id: Optional[str]
    payload: dict
    marker: str


@dataclass(frozen=True)
class MgMigrationPlan:
    ops: list[MgMigrationOp]
    counts_by_type: dict[str, int]
    warnings: list[str]
    skipped_at_plan: int = 0


# ── Helpers de extracción de campos del issue Mantis ──────────────────────


def _get_issue_id(issue: dict) -> str:
    return str(issue.get("id") or issue.get("mantis_issue_id") or "")


def _get_project_id(issue: dict) -> str:
    return str(issue.get("project_id") or "")


def _extract_parent_id(relationships: list[dict[str, Any]]) -> Optional[str]:
    """Busca en las relaciones del issue (forma `{"type": str, "target_issue_id": ...}`,
    ver `adapters/scraping_adapter.py:_parse_relationships_html`) una relación
    "child of" — el único criterio de jerarquía padre/hijo de 2 niveles que
    define este plan (§7: "no hace falta N niveles")."""
    for rel in relationships or []:
        rel_type = str(rel.get("type") or "").strip().lower()
        if "child of" in rel_type:
            target = rel.get("target_issue_id")
            if target is not None:
                return str(target)
    return None


def _build_authorship_block(issue: dict) -> str:
    """Bloque de metadata al inicio de la descripción: autor, asignado y fechas
    de Mantis, con el TEXTO ORIGINAL tal como lo muestra Mantis.

    Este bloque es el **piso de fidelidad** y no se elimina ni cuando el
    backdating de `created_at` funciona: los campos nativos de GitLab pueden
    quedar mal por permisos, por un error de parseo de fecha, o directamente no
    ser seteables (`closed_at` no lo es en ninguna versión de la API v4). El
    texto crudo del origen sobrevive acá pase lo que pase.

    Para tickets cerrados/resueltos en Mantis se agrega una línea explícita de
    fecha de cierre, porque `closed_at` de GitLab NO es seteable por API y va a
    mostrar la fecha de la migración. Sin esta línea, esa fecha se leería como un
    dato real. Se declara como APROXIMACIÓN: la fecha exacta del cambio de estado
    vive en la tabla de historial de Mantis, que hoy el adapter no parsea."""
    reporter = str(issue.get("reporter") or "").strip()
    handler = str(issue.get("handler") or "").strip()
    submitted = str(issue.get("date_submitted") or "").strip()
    updated = str(
        issue.get("last_modified") or issue.get("last_updated") or ""
    ).strip()
    status = str(issue.get("status") or "").strip().lower()

    lineas: list[str] = []
    if reporter:
        lineas.append(f"**Autor original (Mantis):** {reporter}")
    if handler:
        lineas.append(f"**Asignado en Mantis:** {handler}")
    if submitted:
        lineas.append(f"**Fecha de creación (Mantis):** {submitted}")
    if updated:
        lineas.append(f"**Última modificación (Mantis):** {updated}")
    resolucion = str(issue.get("resolution") or "").strip()
    if resolucion:
        lineas.append(f"**Resolución en Mantis:** {resolucion}")
    if status in _MG_STATUS_CERRADOS:
        # `date_closed` es la fecha REAL de cierre, sacada del historial de Mantis
        # (última transición de estado a resolved/closed). `last_modified` sólo se
        # usa como respaldo declarado: cambia con cualquier edición posterior al
        # cierre, así que no es la fecha de cierre — es una aproximación.
        cerrado = str(issue.get("date_closed") or "").strip()
        if cerrado:
            detalle = f"**{cerrado}** (fecha real, del historial de Mantis)"
        elif updated:
            detalle = (
                f"~{updated} (APROXIMACIÓN: es la última modificación, no la fecha "
                "de cierre; el historial de Mantis no fue parseable para este ticket)"
            )
        else:
            detalle = "(el origen no informó fecha)"
        lineas.append(
            f"**Cerrado en Mantis:** estado `{status}` — {detalle}. "
            "El `closed_at` de este issue en GitLab es la fecha de la migración: "
            "`closed_at` no es un parámetro aceptado por la API v4 (verificado "
            "contra GitLab 18.0.2), GitLab lo escribe él mismo al cambiar el "
            "estado. Ver 30_HOMOLOGACION_MANTIS_GITLAB.md §9.2."
        )
    if not lineas:
        return ""
    return "\n".join(f"> {linea}" for linea in lineas)


def _build_description(issue: dict, custom_fields_mode: str) -> str:
    """§5 del plan: description + steps_to_reproduce + additional_information
    concatenados con encabezados Markdown, más el bloque de custom_fields si
    `custom_fields.mode == "metadata_block"`."""
    parts: list[str] = []
    autoria = _build_authorship_block(issue)
    if autoria:
        parts.append(autoria)
    description = (issue.get("description") or "").strip()
    if description:
        parts.append(f"## Descripción\n\n{description}")
    steps = (issue.get("steps_to_reproduce") or "").strip()
    if steps:
        parts.append(f"## Pasos para reproducir\n\n{steps}")
    extra = (issue.get("additional_information") or "").strip()
    if extra:
        parts.append(f"## Información adicional\n\n{extra}")
    if custom_fields_mode == "metadata_block":
        block = map_custom_fields(issue.get("custom_fields") or [])
        if block:
            parts.append(block)
    return "\n\n".join(parts)


def _build_payload(
    issue: dict,
    field_mapping: dict,
    user_mapping: dict,
    warnings: list[str],
    tz_offset: str = "",
) -> dict:
    """Transforma un issue Mantis crudo a un payload de creación GitLab
    aplicando los `mapping/*.py` puros del batch anterior (F3). Nunca
    aborta por un valor sin mapear — cualquier gap se degrada a un
    fallback conocido y se registra en `warnings` (§8.1.4/§8.2.5 del plan:
    "se avisa antes de ejecutar", nunca abort silencioso)."""
    issue_id = _get_issue_id(issue)

    status_cfg = field_mapping.get("status") or {}
    gitlab_state, status_label, used_status_fallback = map_status(issue.get("status", ""), status_cfg)
    if used_status_fallback:
        warnings.append(
            f"issue {issue_id}: status Mantis {issue.get('status')!r} sin mapeo explícito, "
            "usando _unmapped_fallback"
        )

    labels: list[str] = [status_label]

    raw_priority = issue.get("priority")
    if raw_priority not in (None, ""):
        priority_cfg = field_mapping.get("priority") or {}
        # NO se pre-filtra por `int()`: el adapter de SCRAPING entrega el
        # NOMBRE de la prioridad ("high"/"alta"), no el ID numérico de la API
        # REST. `map_priority` acepta ambos (ver `resolve_priority_id`); el
        # pre-chequeo anterior descartaba el 100% de las prioridades leídas
        # por scraping antes siquiera de consultar al mapper.
        try:
            labels.append(
                map_priority(
                    raw_priority,
                    priority_cfg.get("scale") or {},
                    priority_cfg.get("label_prefix", "priority::"),
                )
            )
        except UnmappedPriorityError as exc:
            warnings.append(f"issue {issue_id}: {exc}")

    severity = issue.get("severity")
    if severity:
        severity_cfg = field_mapping.get("severity") or {}
        labels.append(map_severity(severity, severity_cfg.get("label_prefix", "severity::")))

    category = issue.get("category")
    if category:
        category_cfg = field_mapping.get("category") or {}
        labels.append(map_category(category, category_cfg.get("label_prefix", "category::")))

    # RESOLUCIÓN de Mantis. Es lo que distingue un ticket CORREGIDO de uno
    # RECHAZADO (duplicado / no se corregirá / no se requieren cambios) — matiz
    # que antes se perdía por completo: `resolution` no estaba mapeada en ningún
    # lado. NO afecta el estado del issue (eso lo decide `status`, ver §3.1 de
    # 30_HOMOLOGACION_MANTIS_GITLAB.md): sólo aporta trazabilidad.
    resolucion = str(issue.get("resolution") or "").strip()
    if resolucion:
        resolucion_cfg = field_mapping.get("resolution") or {}
        prefijo = resolucion_cfg.get("label_prefix", "mantis-resolution::")
        # `open` es el valor por defecto de Mantis para todo ticket sin resolver:
        # etiquetarlo sería ruido en cada issue abierto.
        if resolucion.lower() != "open":
            labels.append(f"{prefijo}{resolucion}")

    tags_cfg = field_mapping.get("tags") or {}
    labels.extend(map_tags(issue.get("tags") or [], tags_cfg.get("label_prefix", "tag::")))

    version_cfg = field_mapping.get("version") or {}
    version_result = map_version(
        issue.get("target_version"),
        issue.get("fixed_in_version"),
        issue.get("affects_version") or issue.get("version"),
        version_cfg,
    )
    labels.extend(version_result["labels"])

    assignee = None
    handler = issue.get("handler")
    if handler:
        try:
            assignee = map_user(handler, user_mapping or {})
        except UserMappingError as exc:
            warnings.append(f"issue {issue_id}: {exc}")

    custom_fields_cfg = field_mapping.get("custom_fields") or {}
    description = _build_description(issue, custom_fields_cfg.get("mode", "metadata_block"))

    marker = _MG_MARKER_TEMPLATE.format(project_id=_get_project_id(issue), issue_id=issue_id)
    description = f"{description}\n\n{marker}" if description else marker

    # FECHAS. `created_at` es el ÚNICO campo de fecha de la issue que la API v4
    # deja setear, y sólo en el POST de creación (no en el PUT) — verificado
    # contra GitLab 18.0.2: `CreateIssueInput.createdAt` existe en el schema
    # GraphQL ("only for admins and project owners") y `UpdateIssueInput` no
    # tiene ni `updatedAt` ni `closedAt`. Si el parseo de la fecha falla, se
    # OMITE el campo y se avisa: nunca se sustituye por `now()`, porque una
    # fecha inventada es peor que una fecha ausente (la real igual sobrevive en
    # el bloque de metadata de la descripción).
    # `tz_offset` NO es opcional en la práctica: sin él el ISO sale sin offset y
    # GitLab lo interpreta como UTC, con un corrimiento igual al offset real de la
    # instancia Mantis (3 h para Argentina). Con 1008 issues y 2888 notas eso son
    # ~3900 timestamps desplazados. Se detectó auditando los payloads ANTES de
    # migrar: el volcado mostraba `created_at='2025-11-21T11:52:00'` pelado
    # mientras el config declaraba `-03:00`.
    fechas = extraer_fechas_issue(issue, tz_offset)
    payload: dict = {
        "title": issue.get("summary", ""),
        "description": description,
        "state": gitlab_state,
        "labels": labels,
        "milestone": version_result["milestone"],
        "assignee": assignee,
    }
    if fechas["created_at_iso"]:
        payload["created_at"] = fechas["created_at_iso"]
    elif fechas["created_at_raw"]:
        warnings.append(
            f"issue {issue_id}: no se pudo interpretar la fecha de creación de Mantis "
            f"{fechas['created_at_raw']!r}; el issue se crea sin backdating "
            "(la fecha queda en el bloque de metadata)"
        )
    # `updated_at` NO va acá: la API sólo lo acepta en el PUT, y el PUT tiene que
    # ser la ÚLTIMA escritura del pipeline (si no, una nota o un adjunto
    # posterior lo vuelve a poner en `now()`). Lo aplica la pasada de estados.
    if fechas["updated_at_iso"]:
        payload["updated_at"] = fechas["updated_at_iso"]
    return payload


# ── plan_migration (invariante READ-ONLY) ─────────────────────────────────


def plan_migration(
    origin_adapter,
    existing_map: dict[str, str],
    field_mapping: dict,
    user_mapping: dict,
    tz_offset: str = "",
) -> MgMigrationPlan:
    """Lee TODO del origen Mantis (solo métodos `fetch_*` de `origin_adapter`,
    que cumple `adapters.base.MantisReadAdapter`) y arma el plan SIN escribir
    nada en el destino.

    `existing_map`: dict `{mantis_issue_id: status}` — mismo shape que
    produce `migrator_mg_map.get_full_mapping` reindexado por issue_id
    (status ∈ pending|done|partial|failed). Un issue con status "done" se
    saltea (idempotencia, §11 del plan); pending/partial/failed se
    re-planifican (no quedan atascados).

    `field_mapping`/`user_mapping`: dicts crudos (misma forma JSON que
    `migration_config.json` §4) — se pasan tal cual a los `mapping/*.py`
    puros de F3, que ya esperan esa forma.

    Orden topológico (2 niveles, §7 del plan): primero issues sin padre,
    después issues con padre (relación "child of" resuelta vía
    `origin_adapter.fetch_relationships`), para que el padre ya exista
    cuando F5/F6 (otro batch) resuelvan el link real contra GitLab.
    """
    issues = origin_adapter.fetch_all_issues()

    warnings: list[str] = []
    skipped_at_plan = 0
    ops: list[MgMigrationOp] = []

    for issue in issues:
        issue_id = _get_issue_id(issue)

        if existing_map.get(issue_id) == "done":
            skipped_at_plan += 1
            continue

        # El LISTADO de Mantis solo trae id/título/estado/prioridad/severidad/
        # categoría — la descripción, el reporter, el asignado y los pasos
        # viven en la PÁGINA DE DETALLE. Sin esta fusión los issues se
        # migraban con el cuerpo VACÍO y sin autoría (así se migraron los 52
        # primeros de Ripley). El detalle manda; la fila del listado aporta
        # lo que el detalle no tenga.
        try:
            detalle = origin_adapter.fetch_issue_detail(issue.get("id"))
        except Exception:
            detalle = {}
            warnings.append(
                f"issue {issue_id}: no se pudo leer el detalle; se migra solo con "
                "los campos del listado (sin descripción ni autoría)"
            )
        issue_completo = dict(issue)
        issue_completo.update({k: v for k, v in (detalle or {}).items() if v not in (None, "", [])})

        try:
            relationships = detalle.get("relationships") if detalle else None
            if relationships is None:
                relationships = origin_adapter.fetch_relationships(issue.get("id"))
        except Exception:
            relationships = []
            warnings.append(f"issue {issue_id}: no se pudieron obtener relaciones")

        parent_id = _extract_parent_id(relationships)
        payload = _build_payload(
            issue_completo, field_mapping, user_mapping, warnings, tz_offset
        )
        marker = _MG_MARKER_TEMPLATE.format(project_id=_get_project_id(issue), issue_id=issue_id)

        ops.append(
            MgMigrationOp(
                op_kind="create_item",
                mantis_issue_id=issue_id,
                dest_parent_mantis_id=parent_id,
                payload=payload,
                marker=marker,
            )
        )

        # Comentarios (§5: notes -> notas GitLab con autoría en el cuerpo).
        try:
            comments = origin_adapter.fetch_comments(issue.get("id"))
        except Exception:
            comments = []
            warnings.append(f"issue {issue_id}: no se pudieron obtener comentarios")
        for index, comment in enumerate(comments):
            ops.append(
                MgMigrationOp(
                    op_kind="post_comment",
                    mantis_issue_id=issue_id,
                    dest_parent_mantis_id=None,
                    payload={
                        "body": _build_comment_body(comment),
                        "private": bool(comment.get("private")),
                        # `created_at` de la nota SÍ lo acepta
                        # `POST /issues/:iid/notes` (admin u owner del proyecto).
                        # `None` si Mantis no dio fecha o no se pudo parsear: el
                        # executor omite el campo y la fecha original igual queda
                        # en el encabezado del cuerpo (`_build_comment_body`).
                        "created_at": extraer_fecha_nota(comment, tz_offset),
                    },
                    marker=_MG_NOTE_MARKER_TEMPLATE.format(
                        project_id=_get_project_id(issue),
                        issue_id=issue_id,
                        note_id=str(comment.get("id") or index),
                    ),
                )
            )

        # Adjuntos (§5: descarga binaria Mantis -> upload/link en GitLab).
        try:
            attachments = origin_adapter.fetch_attachments(issue.get("id"))
        except Exception:
            attachments = []
            warnings.append(f"issue {issue_id}: no se pudieron obtener adjuntos")
        for attachment in attachments:
            ops.append(
                MgMigrationOp(
                    op_kind="upload_attachment",
                    mantis_issue_id=issue_id,
                    dest_parent_mantis_id=None,
                    # Solo METADATOS (serializables): el binario se descarga
                    # en la ejecución, y el `origin_adapter` se inyecta ahí
                    # (no puede viajar en el plan, que se hashea/persiste).
                    payload={"attachment_meta": dict(attachment)},
                    marker=_MG_ATTACH_MARKER_TEMPLATE.format(
                        project_id=_get_project_id(issue),
                        issue_id=issue_id,
                        file_id=str(attachment.get("id") or attachment.get("name") or ""),
                    ),
                )
            )

    # Orden topológico estable: sin padre primero, con padre después. Los
    # comentarios/adjuntos van SIEMPRE después de todos los create_item, ya
    # que necesitan el issue destino ya creado para resolver su iid.
    def _orden(op: MgMigrationOp) -> tuple[int, int]:
        if op.op_kind != "create_item":
            return (2, 0)
        return (
            _MG_TYPE_ORDER["has_parent" if op.dest_parent_mantis_id else "no_parent"],
            0,
        )

    ops.sort(key=_orden)

    counts_by_type: dict[str, int] = {}
    for op in ops:
        counts_by_type[op.op_kind] = counts_by_type.get(op.op_kind, 0) + 1

    return MgMigrationPlan(
        ops=ops,
        counts_by_type=dict(sorted(counts_by_type.items())),
        warnings=warnings,
        skipped_at_plan=skipped_at_plan,
    )


def compute_plan_hash(plan: MgMigrationPlan) -> str:
    """Hash SHA-256 determinista del plan — mismo patrón que
    `_compute_plan_hash` de `api/migrator.py:48-55`: mismo plan -> mismo
    hash; un plan con 1 issue distinto -> hash distinto."""
    sorted_ids = sorted(op.mantis_issue_id for op in plan.ops if op.op_kind == "create_item")
    payload = json.dumps({"ids": sorted_ids, "counts": plan.counts_by_type}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


__all__ = [
    "MgMigrationOp",
    "MgMigrationPlan",
    "compute_plan_hash",
    "plan_migration",
]
