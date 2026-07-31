"""services/gitlab_sync.py — sync GitLab → tabla `tickets` de Stacky (Plan 276 F5).

SALDA LA DEUDA DEL "PLAN 220" FANTASMA. `api/tickets.py` levantaba
`CapabilityUnavailable("tracker.sync.full")` con el texto literal *"Plan 220 lo
implementa"*, y el plan 220 nunca se escribió. Sin este módulo, arreglar el TLS no
alcanza: `GET /api/tickets/hierarchy` lee `session.query(Ticket)` (la BD LOCAL) y
nadie escribía filas de GitLab ahí, así que el grafo seguía devolviendo
`{"epics": [], "orphans": []}` con la conexión perfecta.

LA CLAVE DE UPSERT ES LA TERNA `(stacky_project_name, tracker_type, external_id)`,
NUNCA `ado_id`. Está forzada por el índice UNIQUE `ux_tickets_stacky_tracker_external`
(`models.py:68-77`). `ado_id` acá lleva el **iid** (el número visible DENTRO del
proyecto, que se repite entre proyectos distintos de GitLab) y NO está en el índice:
upsertear por `ado_id` da `IntegrityError` o filas duplicadas, siempre en la SEGUNDA
corrida, y rompe el criterio de idempotencia de esta propia fase.

NUNCA BORRA NADA. Un issue que ya no aparece en el listado de abiertos pasa a
`ado_state="closed"` y cuenta en `removed`; la fila SIGUE EXISTIENDO. Riel del
producto: no destruir datos del operador.

LA QUERY ES DE ABIERTOS Y ESO NO ES UN DETALLE. Se pide
`TrackerQuery(state="open")` explícito, y la semántica de `removed` de arriba
—"lo que no vino en el listado pasa a closed"— SOLO es correcta con esa query. Si
alguna vez alguien la cambia a `state="all"`, la regla de `removed` deja de tener
sentido y hay que revisarla: van juntas, y por eso están documentadas juntas acá.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from db import session_scope
from models import Ticket
from services.project_context import resolve_project_context
from services.tracker_provider import TrackerQuery

logger = logging.getLogger(__name__)

_TITULO_MAX = 500      # Ticket.title es String(500) y es NOT NULL
_TRACKER = "gitlab"


def _a_int(valor) -> Optional[int]:
    """Convierte a int o devuelve None. `_normalize_issue` emite `id`/`iid` como
    STR (`gitlab_provider.py`) y las columnas son Integer."""
    if valor is None:
        return None
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def sync_gitlab_tickets(project_name: str, *, provider=None) -> dict:
    """Trae los issues ABIERTOS de GitLab a la tabla `tickets`.

    Returns:
        La MISMA forma que el sync de ADO —
        `{"fetched", "created", "updated", "removed", "stacky_project_name"}` —
        para que `api/tickets.py` no tenga que cambiar. Suma `skipped`, que es
        aditivo (los issues que no se pudieron identificar).
    """
    ctx = resolve_project_context(project_name)
    if ctx is None:
        raise ValueError(f"No se pudo resolver el contexto del proyecto '{project_name}'")

    if provider is None:
        from services.tracker_provider import get_tracker_provider

        provider = get_tracker_provider(project_name)

    # `state="open"` EXPLÍCITO. El default de TrackerQuery ya es "open"
    # (tracker_provider.py) y daría lo mismo hoy, pero ese default es un detalle de
    # otro módulo que puede cambiar sin que este sync se entere — y la semántica de
    # `removed` de más abajo depende de que la query sea de abiertos.
    items = provider.fetch_open_items(TrackerQuery(state="open"))

    stacky_name = ctx.stacky_project_name
    tracker_project = ctx.tracker_project

    creados = actualizados = salteados = cerrados = 0
    vistos_external: set[int] = set()

    with session_scope() as session:
        for item in items:
            external_id = _a_int(item.get("id"))
            ado_id = _a_int(item.get("iid"))

            # `external_id` es NOT NULL *de hecho* para GitLab: sin él no se puede
            # upsertear sin violar el índice único. Y un `iid` no numérico no puede
            # ir a una columna Integer NOT NULL. Los dos casos se saltean con
            # warning; el sync NUNCA revienta entero por un ítem raro.
            if external_id is None or ado_id is None:
                salteados += 1
                logger.warning(
                    "Plan 276 sync: issue sin identidad numérica usable (id=%r, iid=%r) en "
                    "'%s'; se saltea para no insertar una fila que rompa el índice único.",
                    item.get("id"), item.get("iid"), tracker_project,
                )
                continue

            vistos_external.add(external_id)

            titulo = (item.get("title") or "")[:_TITULO_MAX]
            estado = item.get("state") or "opened"
            tipo = item.get("work_item_type") or "Issue"
            parent_ado_id = _a_int(item.get("parent"))

            # LA BÚSQUEDA VA POR LA TERNA. `tracker_type` y `stacky_project_name`
            # van en el WHERE, no solo en el INSERT: sin el primero, un proyecto
            # Stacky que antes fue ADO machearía filas del tracker viejo y las
            # pisaría; sin el segundo, dos proyectos Stacky apuntando al mismo
            # GitLab se contaminarían.
            fila = (
                session.query(Ticket)
                .filter(
                    Ticket.stacky_project_name == stacky_name,
                    Ticket.tracker_type == _TRACKER,
                    Ticket.external_id == external_id,
                )
                .first()
            )

            if fila is None:
                session.add(
                    Ticket(
                        ado_id=ado_id,
                        external_id=external_id,
                        project=tracker_project,
                        stacky_project_name=stacky_name,
                        tracker_type=_TRACKER,
                        title=titulo,
                        description=item.get("description") or "",
                        ado_state=estado,
                        ado_url=(item.get("web_url") or "")[:400],
                        work_item_type=tipo,
                        parent_ado_id=parent_ado_id,
                        last_synced_at=datetime.utcnow(),
                    )
                )
                creados += 1
                continue

            cambio = (
                fila.title != titulo
                or fila.ado_state != estado
                or fila.work_item_type != tipo
                or fila.parent_ado_id != parent_ado_id
            )
            fila.ado_id = ado_id
            fila.project = tracker_project
            fila.title = titulo
            fila.description = item.get("description") or ""
            fila.ado_state = estado
            fila.ado_url = (item.get("web_url") or "")[:400]
            fila.work_item_type = tipo
            fila.parent_ado_id = parent_ado_id
            fila.last_synced_at = datetime.utcnow()
            if cambio:
                actualizados += 1

        # Lo que dejó de venir en el listado de ABIERTOS se marca cerrado. NO se
        # borra: el operador conserva su historial y el grafo sigue mostrando el ítem.
        if vistos_external:
            pendientes = (
                session.query(Ticket)
                .filter(
                    Ticket.stacky_project_name == stacky_name,
                    Ticket.tracker_type == _TRACKER,
                    Ticket.ado_state != "closed",
                    ~Ticket.external_id.in_(vistos_external),
                )
                .all()
            )
            for fila in pendientes:
                fila.ado_state = "closed"
                fila.last_synced_at = datetime.utcnow()
                cerrados += 1

    resultado = {
        "fetched": len(items),
        "created": creados,
        "updated": actualizados,
        "removed": cerrados,
        "skipped": salteados,
        "stacky_project_name": stacky_name,
    }
    logger.info("Plan 276 sync GitLab '%s': %s", project_name, resultado)
    return resultado


__all__ = ["sync_gitlab_tickets"]
