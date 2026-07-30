"""tools/migrar_mantis_gitlab/migrator_mg_states.py — pasada de aplicación de ESTADO.

## Por qué existe este módulo

`field_mapping.status` del `migration_config.json` define, para cada status de
Mantis, un `gitlab_state` (`opened`/`closed`), y `migrator_mg_core._build_payload`
lo calcula correctamente y lo pone en `payload["state"]`. **Pero ese valor nunca
llegaba a GitLab.** `destination_writer.GitLabDestinationWriter.create_item`
mete todo lo que no sea `title`/`description`/`labels`/`assignee` en
`TrackerItem.fields`, y `GitLabTrackerProvider.create_item`
(`services/gitlab_provider.py:296-320`) no envía `fields` a la API. El comentario
del writer prometía que "un batch posterior (F5/F6) decida cómo aplicarlos" —
ese batch nunca se escribió. Resultado real medido contra Ripley (proyecto GitLab
127): 52 issues migradas, **52 abiertas y 0 cerradas**, incluida una con label
`status::resolved`.

Este módulo es ese paso faltante.

## Por qué NO se basa en `plan.ops`

Sería lo natural (la op `create_item` ya trae `payload["state"]`), y sería un
error. `plan_migration` **saltea** todo issue cuyo mapeo esté en `"done"`
(`migrator_mg_core.py:304-306`), y `hydrate_map_from_destination_mg` marca `done`
a todos los que ya tienen marker en el destino. O sea: en una re-corrida, las
issues YA migradas no generan ninguna op, así que un paso de estados alimentado
por `plan.ops` **jamás repararía lo ya migrado** — que es justamente el caso a
arreglar. Por eso la pasada recorre el universo del ORIGEN cruzado contra el
mapeo persistido, no el plan.

## Idempotencia

No hace falta ningún marcador ni tabla nueva: **el propio estado del issue en
GitLab es la marca**. Se lee el estado real del destino y sólo se emite el `PUT`
cuando difiere del deseado. Correr esta pasada N veces produce el mismo resultado
que correrla una vez, y una corrida sin diferencias no hace ni una escritura.

## Simetría cerrar/reabrir

La pasada es bidireccional a propósito. Un proceso que sólo cierre deja las
reaperturas de Mantis (`resolved` → `feedback` + `resolution=reopened`)
invisibles para siempre en GitLab.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .destination_writer import DestinationWriter
from .mapping.date_map import extraer_fechas_issue
from .mapping.status_map import map_status

_LOGGER_NAME = "migrar_mantis_gitlab.states"

# Marcador de la nota de trazabilidad del cierre. Deliberadamente distinto del
# marcador de issue (`stacky-migrated:mantis:{p}:{i}`) y del de nota
# (`...:{note_id}`) para que `comment_exists` no confunda una nota migrada de
# Mantis con esta anotación del migrador.
_MG_STATE_NOTE_MARKER = "<!-- stacky-migrated:mantis:{project_id}:{issue_id}:state -->"

_VALID_STATES = frozenset({"opened", "closed"})


@dataclass(frozen=True)
class MgStateChange:
    """Un cambio de estado pendiente, ya resuelto contra el destino."""

    mantis_issue_id: str
    gitlab_iid: str
    mantis_status: str
    current_state: str
    desired_state: str
    #  ISO 8601 de la última modificación en Mantis, o `None`. Se manda como
    #  `updated_at` en el MISMO PUT del cierre: es el único campo de fecha que la
    #  API v4 acepta en el update, y esta pasada es la última escritura del
    #  pipeline, así que es el único momento en que setearlo no lo pisa nada.
    updated_at_iso: Optional[str] = None
    #  Texto crudo de la fecha de Mantis para citarla en la nota de cierre:
    #  `date_closed` (real, del historial) si está, si no `last_modified`.
    mantis_date_raw: str = ""
    #  `True` sólo si `mantis_date_raw` es la fecha REAL de cierre. Con `False` la
    #  nota tiene que decir que es una aproximación — presentar un proxy como dato
    #  exacto es peor que no dar fecha.
    fecha_cierre_es_real: bool = False

    @property
    def action(self) -> str:
        """`close` o `reopen` — el `state_event` que espera la API v4."""
        return "close" if self.desired_state == "closed" else "reopen"


@dataclass
class MgStateResult:
    applied: int = 0
    already_ok: int = 0
    #  Tickets del origen que no tienen `gitlab_iid` en el mapeo: no están
    #  migrados todavía. NO es un error de esta pasada (los crea `execute`),
    #  pero se declara para que el reporte no lo esconda.
    not_migrated: list[str] = field(default_factory=list)
    #  Tickets cuyo status de Mantis cayó a `_unmapped_fallback`: el estado
    #  aplicado es el del fallback, no uno derivado del status real.
    unmapped_status: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    changes: list[MgStateChange] = field(default_factory=list)

    @property
    def to_close(self) -> int:
        return sum(1 for c in self.changes if c.desired_state == "closed")

    @property
    def to_reopen(self) -> int:
        return sum(1 for c in self.changes if c.desired_state == "opened")


def _get_issue_id(issue: dict) -> str:
    return str(issue.get("id") or issue.get("mantis_issue_id") or "")


def plan_state_changes(
    origin_issues: list[dict],
    field_mapping_status: dict,
    mapping_lookup: dict[str, str],
    destination_states: dict[str, str],
    tz_offset: str = "",
) -> MgStateResult:
    """Función PURA: calcula qué issues hay que cerrar o reabrir. No escribe.

    - `origin_issues`: lo que devuelve `origin_adapter.fetch_all_issues()`.
    - `field_mapping_status`: el dict crudo de `field_mapping.status` (§4 del
      config), el mismo que consume `mapping.status_map.map_status`.
    - `mapping_lookup`: `{mantis_issue_id: gitlab_iid}` (de `get_full_mapping`).
    - `destination_states`: `{gitlab_iid: "opened"|"closed"}` leído del destino.

    Devuelve un `MgStateResult` con `changes` poblado y los contadores de
    diagnóstico, pero con `applied=0` — aplicar es tarea de
    `apply_state_changes`.
    """
    result = MgStateResult()

    for issue in origin_issues:
        issue_id = _get_issue_id(issue)
        if not issue_id:
            continue

        desired_state, _label, used_fallback = map_status(
            issue.get("status", ""), field_mapping_status
        )
        if used_fallback:
            result.unmapped_status.append(issue_id)

        if desired_state not in _VALID_STATES:
            # Config inválida (p. ej. `gitlab_state: "cerrado"`). No se adivina:
            # `config_schema` debería atajarlo antes, pero si llega hasta acá se
            # declara y se saltea en vez de emitir un PUT con basura.
            result.failed.append({
                "mantis_issue_id": issue_id,
                "error": (
                    f"field_mapping.status define gitlab_state={desired_state!r}, "
                    f"que no es 'opened' ni 'closed'."
                ),
            })
            continue

        gitlab_iid = mapping_lookup.get(issue_id)
        if not gitlab_iid:
            result.not_migrated.append(issue_id)
            continue

        current_state = (destination_states.get(str(gitlab_iid)) or "").strip().lower()
        if current_state == desired_state:
            result.already_ok += 1
            continue
        if current_state not in _VALID_STATES:
            # El destino no informó un estado reconocible para ese iid (issue
            # borrado a mano, o no vino en el barrido). Se declara y NO se toca:
            # un PUT a ciegas acá podría reabrir algo cerrado a propósito.
            result.failed.append({
                "mantis_issue_id": issue_id,
                "error": (
                    f"no se pudo leer el estado actual del issue GitLab #{gitlab_iid} "
                    f"(valor leído: {current_state!r}). Se omite por seguridad."
                ),
            })
            continue

        fechas = extraer_fechas_issue(issue, tz_offset)
        # Para la nota de cierre se prefiere `date_closed` (fecha REAL, del
        # historial de Mantis) sobre `last_modified` (aproximación que cambia con
        # cualquier edición posterior al cierre). El flag deja constancia de cuál
        # de las dos se usó, para que la nota no presente una aproximación como
        # dato exacto.
        cierre_raw = str(issue.get("date_closed") or "").strip()
        result.changes.append(
            MgStateChange(
                mantis_issue_id=issue_id,
                gitlab_iid=str(gitlab_iid),
                mantis_status=str(issue.get("status", "")),
                current_state=current_state,
                desired_state=desired_state,
                updated_at_iso=fechas["updated_at_iso"],
                mantis_date_raw=cierre_raw or fechas["updated_at_raw"],
                fecha_cierre_es_real=bool(cierre_raw),
            )
        )

    return result


def apply_state_changes(
    result: MgStateResult,
    writer: DestinationWriter,
    *,
    mantis_project_id: str,
    closure_note: bool = True,
    mantis_status_dates: Optional[dict[str, str]] = None,
) -> MgStateResult:
    """Aplica los `result.changes` contra el destino. Muta y devuelve `result`.

    `closure_note=True` deja, en cada issue que se CIERRA, una nota que declara
    que el cierre lo hizo la migración y que el `closed_at` de GitLab no es la
    fecha real de cierre en Mantis (la API v4 no permite setear `closed_at`).
    Sin esa nota, la fecha de cierre de GitLab se lee como un dato real y no lo
    es. La nota es idempotente por marcador (`comment_exists`).

    `mantis_status_dates`: `{mantis_issue_id: fecha}` opcional, para que la nota
    pueda citar la fecha real del origen cuando el adapter la haya leído.

    Un fallo en un issue NO aborta la pasada (mismo criterio que
    `execute_migration`): se registra en `result.failed` y se sigue.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    dates = mantis_status_dates or {}

    for change in result.changes:
        try:
            # `updated_at` va en el MISMO PUT que el cierre: es el último write
            # del pipeline, así que nada posterior lo pisa con `now()`.
            writer.apply_item_state(
                change.gitlab_iid,
                change.desired_state,
                updated_at=change.updated_at_iso,
            )

            if closure_note and change.desired_state == "closed":
                marker = _MG_STATE_NOTE_MARKER.format(
                    project_id=mantis_project_id, issue_id=change.mantis_issue_id
                )
                if not writer.comment_exists(change.gitlab_iid, marker):
                    # La fecha se toma del override explícito si el caller lo
                    # pasó (p. ej. una fecha de cierre sacada del historial de
                    # Mantis); si no, del texto crudo de última modificación, que
                    # para un ticket ya cerrado es la mejor aproximación
                    # disponible. Se declara como aproximación, no como dato.
                    override = dates.get(change.mantis_issue_id)
                    fecha = override or change.mantis_date_raw
                    if fecha and (override or change.fecha_cierre_es_real):
                        sufijo = (
                            f" Fecha de cierre en Mantis: **{fecha}** "
                            "(fecha real, tomada del historial de la incidencia)."
                        )
                    elif fecha:
                        sufijo = (
                            f" Última modificación en Mantis: **{fecha}** "
                            "(APROXIMACIÓN: el historial de Mantis no fue parseable "
                            "para este ticket, así que ésta no es necesariamente la "
                            "fecha de cierre)."
                        )
                    else:
                        sufijo = " El origen no informó fecha."
                    writer.post_comment(
                        change.gitlab_iid,
                        "_Cerrado por la migración desde Mantis: el ticket "
                        f"{change.mantis_issue_id} está en estado "
                        f"`{change.mantis_status}`.{sufijo} El `closed_at` de este "
                        "issue en GitLab es la fecha de la migración, **no** la "
                        "fecha real de cierre en Mantis: `closed_at` no es un "
                        "parámetro aceptado por la API v4 (verificado contra "
                        "GitLab 18.0.2), GitLab lo escribe él mismo al cambiar el "
                        "estado._"
                        f"\n\n{marker}",
                        created_at=change.updated_at_iso,
                    )

            result.applied += 1
            logger.info(
                "estado aplicado: mantis %s -> issue #%s (%s -> %s, status=%s, updated_at=%s)",
                change.mantis_issue_id, change.gitlab_iid,
                change.current_state, change.desired_state, change.mantis_status,
                change.updated_at_iso or "(sin backdating)",
            )
        except Exception as exc:
            logger.warning(
                "no se pudo aplicar el estado del issue #%s (mantis %s): %s",
                change.gitlab_iid, change.mantis_issue_id, exc,
            )
            result.failed.append({
                "mantis_issue_id": change.mantis_issue_id,
                "gitlab_iid": change.gitlab_iid,
                "op_kind": "apply_item_state",
                "error": str(exc),
            })

    return result


def fetch_destination_states(writer: DestinationWriter) -> dict[str, str]:
    """`{gitlab_iid: state}` de TODOS los items del destino, en UNA pasada.

    `writer.fetch_open_items()` ya pide `TrackerQuery(state="all")`
    (`destination_writer.py:213-224`), así que incluye los cerrados —
    imprescindible: si sólo viera los abiertos, la pasada intentaría cerrar de
    nuevo lo ya cerrado en cada corrida, y no podría detectar reaperturas.
    """
    states: dict[str, str] = {}
    for item in writer.fetch_open_items():
        iid = str(item.get("iid") or item.get("id") or "")
        if iid:
            states[iid] = str(item.get("state") or "")
    return states


__all__ = [
    "MgStateChange",
    "MgStateResult",
    "apply_state_changes",
    "fetch_destination_states",
    "plan_state_changes",
]
