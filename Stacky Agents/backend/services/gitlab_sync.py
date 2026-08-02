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

import config  # importado a nivel módulo para poder parchear en tests
from db import session_scope
from models import Ticket
from services.project_context import resolve_project_context
from services.tracker_provider import TrackerQuery

logger = logging.getLogger(__name__)

_TITULO_MAX = 500      # Ticket.title es String(500) y es NOT NULL
_TRACKER = "gitlab"

# Plan 277 F6 — tope duro de padres traídos de a uno en una corrida. No es "por si
# acaso": son N requests contra el GitLab del operador y la cota es lo que impide
# que un proyecto con etiquetas rotas dispare cientos.
_TOPE_PADRES = 50


# Plan 277 F4 — los 4 contadores de la clasificación local. Son ADITIVOS al dict de
# retorno: `fetched/created/updated/removed/skipped` no cambian, así que el consumidor
# (`api/tickets.py:5995-6021`) sigue andando sin tocar una línea.
_CONTADORES_LOCAL = (
    "usados_local_tipo",     # GitLab no dijo nada y se aplicó la clasificación local
    "superseded_tipo",       # GitLab dijo algo distinto: gana GitLab, la local NO se borra
    "usados_local_padre",
    "superseded_padre",
)


def _a_int(valor) -> Optional[int]:
    """Convierte a int o devuelve None. `_normalize_issue` emite `id`/`iid` como
    STR (`gitlab_provider.py`) y las columnas son Integer."""
    if valor is None:
        return None
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _clasificacion_local_habilitada() -> bool:
    """Plan 277 F4 — STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED (default True).

    `config` acá es el MÓDULO (este archivo hace `import config` "para poder parchear
    en tests"); la instancia de flags es `config.config`, igual que la lectura de la
    flag del contrato en `_upsert_ticket_gitlab`.
    """
    return bool(
        getattr(config.config, "STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED", True)
    )


def _sync_parents_habilitado() -> bool:
    """Plan 277 F6 — STACKY_GITLAB_SYNC_PARENTS_ENABLED (default True).

    Mismo patrón que la flag de arriba: `config` es el MÓDULO y la instancia de
    flags es `config.config`.
    """
    return bool(getattr(config.config, "STACKY_GITLAB_SYNC_PARENTS_ENABLED", True))


def _padre_del_item(item: dict) -> Optional[int]:
    """El padre que el contrato declara para este item, o None con la flag apagada.

    UN SOLO LUGAR lee esta decisión: la usa el upsert (para escribir la columna) y
    el bucle del sync (para juntar los padres referenciados). Dos lecturas separadas
    divergirían en el primer cambio y F6 saldría a pedir padres que el upsert después
    descarta.
    """
    if not bool(getattr(config.config, "STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED", True)):
        return None
    return _a_int(item.get("parent"))


def _sumar(contadores: Optional[dict], clave: str) -> None:
    """Incrementa un contador si el llamador pidió llevarlos. No-op si es None."""
    if contadores is None:
        return
    contadores[clave] = contadores.get(clave, 0) + 1


def _upsert_ticket_gitlab(
    session, item: dict, *, ctx, ahora: datetime, contadores: Optional[dict] = None
) -> str:
    """Alta/actualización de UNA fila de GitLab por la terna. Plan 277 F2.

    Extraído tal cual del bucle de `sync_gitlab_tickets` (antes gitlab_sync.py:110-158)
    para que F6 traiga los padres faltantes por el MISMO camino. No cambia una sola
    regla: misma clave de upsert, mismo mapeo de campos, misma comparación previa.

    Recibe el `item` CRUDO y no los campos ya mapeados —a propósito—: si el mapeo
    quedara afuera, F6 tendría que copiarlo, y dos copias de un mapeo es exactamente
    la enfermedad de "N motores" que este plan existe para curar. Por el mismo
    motivo el guard de la flag vive acá adentro y no en el bucle.

    El llamador conserva el guard de identidad (`external_id`/`ado_id` no nulos):
    es él quien lleva la cuenta de salteados y el set de `vistos_external`.

    Plan 277 F4 — CLASIFICACIÓN LOCAL Y SU CASO BORDE. `contadores` es un dict
    opcional que esta función INCREMENTA (ver `_CONTADORES_LOCAL`); el valor de
    retorno no cambia, para no romper a los llamadores del 277 F2. La precedencia es
    la de §3.2 sin excepciones: GitLab es el sistema de registro y la clasificación
    local SOLO llena el vacío.

    CASO BORDE, declarado a propósito: en la PRIMERA aparición de un issue
    `fila is None` — la fila todavía no existe, así que no hay clasificación local
    que aplicar y los 4 contadores quedan en 0. Eso es correcto, no un bug: el
    operador clasifica un ticket que YA está en la tabla, y su clasificación se
    aplica desde el sync SIGUIENTE.

    Returns: "created" | "updated" | "noop"
    """
    external_id = _a_int(item.get("id"))
    ado_id = _a_int(item.get("iid"))

    titulo = (item.get("title") or "")[:_TITULO_MAX]
    estado = item.get("state") or "opened"
    tipo = item.get("work_item_type") or "Issue"

    # Plan 277 F2 — con el contrato apagado el sync se comporta EXACTO como en
    # 276: sin padre por etiqueta. La flag gatea SOLO el padre y NUNCA el tipo,
    # porque `work_item_type` ya lo poblaba el plan 276 y apagarlo sería una
    # regresión, no un rollback.
    parent_ado_id = _padre_del_item(item)

    # LA BÚSQUEDA VA POR LA TERNA. `tracker_type` y `stacky_project_name`
    # van en el WHERE, no solo en el INSERT: sin el primero, un proyecto
    # Stacky que antes fue ADO machearía filas del tracker viejo y las
    # pisaría; sin el segundo, dos proyectos Stacky apuntando al mismo
    # GitLab se contaminarían.
    fila = (
        session.query(Ticket)
        .filter(
            Ticket.stacky_project_name == ctx.stacky_project_name,
            Ticket.tracker_type == _TRACKER,
            Ticket.external_id == external_id,
        )
        .first()
    )

    # Plan 277 F4 — GitLab es el sistema de registro (§3.2). La clasificación local
    # SOLO llena el vacío; si GitLab dijo algo, gana GitLab y la local queda como
    # `superseded` (contada, NUNCA borrada: es dato del operador). Va DESPUÉS de
    # buscar la fila y ANTES de escribirla, porque necesita las dos cosas.
    if _clasificacion_local_habilitada() and fila is not None:
        origen_tipo = item.get("origen_tipo") or "defecto"
        if origen_tipo == "defecto" and fila.local_work_item_type:
            tipo = fila.local_work_item_type
            _sumar(contadores, "usados_local_tipo")
        elif (
            origen_tipo != "defecto"
            and fila.local_work_item_type
            and fila.local_work_item_type != tipo
        ):
            _sumar(contadores, "superseded_tipo")

        if parent_ado_id is None and fila.local_parent_iid:
            parent_ado_id = fila.local_parent_iid
            _sumar(contadores, "usados_local_padre")
        elif (
            parent_ado_id is not None
            and fila.local_parent_iid
            and fila.local_parent_iid != parent_ado_id
        ):
            _sumar(contadores, "superseded_padre")

    if fila is None:
        session.add(
            Ticket(
                ado_id=ado_id,
                external_id=external_id,
                project=ctx.tracker_project,
                stacky_project_name=ctx.stacky_project_name,
                tracker_type=_TRACKER,
                title=titulo,
                description=item.get("description") or "",
                ado_state=estado,
                ado_url=(item.get("web_url") or "")[:400],
                work_item_type=tipo,
                parent_ado_id=parent_ado_id,
                last_synced_at=ahora,
            )
        )
        return "created"

    cambio = (
        fila.title != titulo
        or fila.ado_state != estado
        or fila.work_item_type != tipo
        or fila.parent_ado_id != parent_ado_id
    )
    fila.ado_id = ado_id
    fila.project = ctx.tracker_project
    fila.title = titulo
    fila.description = item.get("description") or ""
    fila.ado_state = estado
    fila.ado_url = (item.get("web_url") or "")[:400]
    fila.work_item_type = tipo
    fila.parent_ado_id = parent_ado_id
    fila.last_synced_at = ahora
    return "updated" if cambio else "noop"


def sync_gitlab_tickets(project_name: str, *, provider=None, forzar_full: bool = False) -> dict:
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

    # ── Plan 292 — el modo se decide ANTES de armar la query ────────────────
    # El docstring de este módulo (:21-25) anticipó exactamente este cambio: la
    # query de abiertos y la regla de `removed` "van juntas". Acá se cumple esa
    # advertencia — cuando la query deja de ser de abiertos, la regla se APAGA.
    from services import gitlab_sync_watermark as _wm

    modo, motivo, marca, contador_previo = _wm.decidir_modo_de_sync(
        ctx.stacky_project_name, forzar_full=forzar_full
    )
    if modo == "incremental":
        # `state="all"` a propósito: con `state="open"` un issue CERRADO después
        # de la marca no vendría en la respuesta y el cierre sería INDETECTABLE
        # (ni por presencia ni por ausencia, que está apagada). Con "all" viene
        # con state="closed" y `_upsert_ticket_gitlab` lo refleja solo (:227).
        # `_query_to_gitlab_params` no emite `state` para "all" (gitlab_provider
        # .py:124-127) y GitLab sin `state` devuelve todos.
        consulta = TrackerQuery(state="all", updated_after=marca)
    else:
        # `state="open"` EXPLÍCITO. El default de TrackerQuery ya es "open"
        # (tracker_provider.py) y daría lo mismo hoy, pero ese default es un detalle
        # de otro módulo que puede cambiar sin que este sync se entere — y la
        # semántica de `removed` de más abajo depende de que la query sea de
        # abiertos. BYTE-IDÉNTICO a lo que había antes de este plan.
        consulta = TrackerQuery(state="open")
    items = provider.fetch_open_items(consulta)

    stacky_name = ctx.stacky_project_name
    tracker_project = ctx.tracker_project

    creados = actualizados = salteados = cerrados = 0
    # Plan 292 §3.1-bis — arranca SIEMPRE en 0, igual que los contadores del 277:
    # una clave que aparece y desaparece es peor que una en cero.
    omitidos_cerrados_desconocidos = 0
    vistos_external: set[int] = set()
    # Plan 277 F6 — los iid que las etiquetas de padre nombraron durante el bucle.
    # Se declara ACÁ (no adentro) porque el bloque que trae los faltantes corre
    # después, y se puebla en la misma línea donde se calcula el padre del item.
    parents_vistos: set[int] = set()
    padres_traidos = padres_fallidos = padres_omitidos_por_tope = 0
    # Plan 277 F4 — los 4 contadores arrancan SIEMPRE en 0, incluso con la flag
    # apagada: el consumidor lee claves fijas y una clave que aparece y desaparece
    # es peor que una en cero.
    contadores_local: dict = {clave: 0 for clave in _CONTADORES_LOCAL}

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

            # ── Plan 292 v2 §3.1-bis — la barrera de admisión ────────────────
            # `state="all"` no sólo LEE distinto: haría que un issue CERRADO y
            # desconocido localmente se INSERTE como fila nueva (la rama
            # `if fila is None` del upsert no mira el estado). Hoy esa fila no
            # existe, nadie la borra nunca, y `list_tickets` la mostraría arriba
            # del tablero comiéndose una de las 500 posiciones. Ver §2.7.
            #
            # EL SELECT SOLO SE PAGA EN MODO PARCIAL. `admitir_del_delta` ya
            # devuelve True de entrada en modo completo, así que consultar la
            # existencia ahí sería un SELECT por ítem (63 en RIPLEY) para una
            # respuesta que no se mira. En estado estable el delta es de 0 ítems,
            # así que el costo real es CERO. No se optimiza a un `IN` masivo por
            # adelantado: sería una abstracción prematura sobre un camino que casi
            # siempre está vacío.
            _existe = modo == "incremental" and (
                session.query(Ticket.id)
                .filter(
                    Ticket.stacky_project_name == stacky_name,
                    Ticket.tracker_type == _TRACKER,
                    Ticket.external_id == external_id,
                )
                .first()
                is not None
            )
            if not _wm.admitir_del_delta(item, fila_existe=_existe, modo=modo):
                omitidos_cerrados_desconocidos += 1
                # SALE de `vistos_external`: no vino a decir que sigue abierto.
                # Hoy ningún camino lo consume —el bloque de ausencia sólo corre
                # en modo completo, donde la barrera nunca saltea nada—, pero el
                # conjunto tiene que significar exactamente una cosa: "GitLab lo
                # listó como parte del universo consultado". Un conjunto con dos
                # significados es cómo nace el próximo bug de esta familia.
                vistos_external.discard(external_id)
                continue

            parent_del_item = _padre_del_item(item)
            if parent_del_item:
                parents_vistos.add(parent_del_item)

            # Plan 277 F2 — el upsert vive en `_upsert_ticket_gitlab` para que F6
            # traiga los padres faltantes por el MISMO camino. Acá solo se cuenta
            # por su valor de retorno.
            resultado_fila = _upsert_ticket_gitlab(
                session, item, ctx=ctx, ahora=datetime.utcnow(),
                contadores=contadores_local,
            )
            if resultado_fila == "created":
                creados += 1
            elif resultado_fila == "updated":
                actualizados += 1

        # Lo que dejó de venir en el listado de ABIERTOS se marca cerrado. NO se
        # borra: el operador conserva su historial y el grafo sigue mostrando el ítem.
        #
        # Plan 292 — LA REGLA DE AUSENCIA SOLO ES VALIDA EN MODO COMPLETO.
        # En modo parcial la respuesta NO contiene todo lo abierto, así que este
        # bloque marcaría `closed` todo lo que no cambió: medido, un delta de 1
        # ítem sobre 3 filas cierra 2. La condición NO es "hay flag": es "la query
        # fue de abiertos". Van juntas, tal como avisa el docstring de :21-25.
        if modo == "completo" and vistos_external:
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

        # ── Plan 277 F6 — traer los padres que el listado de ABIERTOS no trajo ──
        # La query es `state="open"`: una épica CERRADA no viene, así que sus hijos
        # apuntan a un `parent_ado_id` que no está en la BD y el grafo los manda a
        # `orphans`. Se piden UNO A UNO, y solo, los iid que las etiquetas nombraron
        # y no llegaron.
        #
        # VA DESPUÉS del bloque de cerrados a propósito: un padre traído acá NO está
        # en `vistos_external` (no vino en el listado), así que si corriera antes el
        # bloque de arriba lo contaría como `removed` y le pisaría el estado.
        #
        # UNA SOLA PASADA, también a propósito: si el padre traído cuelga a su vez de
        # otra épica ausente, esa NO se busca. Es una decisión —evita una recursión de
        # N requests contra el sistema del operador—: el hijo queda colgando de su
        # padre inmediato y el abuelo aparece como `padre_ausente_en_bd` en el motivo
        # del huérfano, que es exactamente la señal que el operador necesita.
        if _sync_parents_habilitado():
            # `session_scope` usa `autoflush=False` (db.py:39): sin este flush la
            # query de abajo NO ve lo que el bucle acaba de insertar con `add()` y
            # el sync saldría a pedir padres que ya están en la base.
            session.flush()
            referenciados = {p for p in parents_vistos if p}
            presentes = {
                fila_id
                for (fila_id,) in session.query(Ticket.ado_id).filter(
                    Ticket.stacky_project_name == stacky_name,
                    Ticket.tracker_type == _TRACKER,
                )
            }
            faltantes_todos = sorted(referenciados - presentes)
            faltantes = faltantes_todos[:_TOPE_PADRES]
            padres_omitidos_por_tope = max(0, len(faltantes_todos) - _TOPE_PADRES)
            # EL TOPE SE LOGUEA SIEMPRE QUE RECORTA, con el número real: una cota
            # silenciosa se lee como "trajimos todos" cuando no fue así.
            if padres_omitidos_por_tope:
                logger.warning(
                    "Plan 277: %d padres faltantes exceden el tope de %d; se traen los "
                    "primeros %d y quedan %d sin traer.",
                    len(faltantes_todos), _TOPE_PADRES, _TOPE_PADRES,
                    padres_omitidos_por_tope,
                )
            ahora_padres = datetime.utcnow()
            for iid in faltantes:
                try:
                    # `get_item` devuelve `_normalize_issue(body)` (gitlab_provider.py
                    # :280-283): YA pasó por el contrato y trae work_item_type/parent,
                    # el mismo shape que consume el bucle principal. Por eso el upsert
                    # se reusa tal cual.
                    body = provider.get_item(str(iid))
                except Exception as exc:
                    # Un padre roto NO tumba la corrida: se cuenta, se avisa y sigue.
                    padres_fallidos += 1
                    logger.warning(
                        "Plan 277: no se pudo traer el padre iid=%s: %s", iid, exc
                    )
                    continue
                # MISMO upsert que el bucle principal (F2 lo extrajo para esto). NO se
                # copia el bloque: dos upserts divergentes es el bug que el plan cura.
                _upsert_ticket_gitlab(
                    session, body, ctx=ctx, ahora=ahora_padres,
                    contadores=contadores_local,
                )
                padres_traidos += 1

    # ── Plan 292 — avanzar la marca ────────────────────────────────────────
    # Se hace DESPUÉS de cerrar la sesión: si la transacción falla, `session_scope`
    # levanta y no se llega acá, así que la marca NUNCA avanza sobre datos que no
    # se guardaron. El orden importa y es deliberado.
    nueva = _wm.marca_maxima([i.get("updated_at") for i in items])
    # `marca_maxima` devuelve None con la tanda vacía o toda inválida, y
    # `escribir_marca` con None CONSERVA la marca anterior: un delta vacío
    # significa "no cambió nada", nunca "avanzá el reloj".
    _wm.escribir_marca(
        stacky_name, nueva, 0 if modo == "completo" else contador_previo + 1
    )

    # ── Plan 292 v2 [ADICIÓN ARQUITECTO] — el ahorro se mide solo ───────────
    # El tamaño serializado de lo que GitLab mandó. NO es el byte exacto del
    # cable (falta compresión y cabeceras) y por eso el nombre dice "recibidos"
    # y no "transferidos": lo que interesa es la SERIE, no el valor absoluto.
    # En estado estable esta clave cae a 0 y el operador lo ve en su propio log,
    # sin que nadie le pregunte nada a GitLab.
    #
    # LA TANDA VACIA VALE 0, NO 2. `json.dumps([])` son los dos bytes de "[]",
    # que son ENVOLTORIO y no carga: contarlos dejaría el KPI en 2 para siempre y
    # el operador no vería nunca el cero que el plan promete.
    # Best-effort: un ítem no serializable NO puede tumbar un sync que ya
    # terminó bien.
    try:
        import json as _json

        bytes_recibidos = len(_json.dumps(items, default=str).encode("utf-8")) if items else 0
    except Exception:  # noqa: BLE001
        bytes_recibidos = -1

    resultado = {
        "fetched": len(items),
        "created": creados,
        "updated": actualizados,
        "removed": cerrados,
        "skipped": salteados,
        "stacky_project_name": stacky_name,
        # Plan 277 F4 — ADITIVO: las 5 claves de arriba conservan su significado.
        **contadores_local,
        # Plan 277 F6 — también ADITIVO. `padres_traidos` NO se suma a `created`:
        # `created` sigue significando "issues abiertos del listado".
        "padres_traidos": padres_traidos,
        "padres_fallidos": padres_fallidos,
        "padres_omitidos_por_tope": padres_omitidos_por_tope,
        # Plan 292 — ADITIVO. El consumidor (api/tickets.py) lee
        # created/updated/removed y sigue andando sin tocar una línea.
        "modo_sync": modo,
        "motivo_modo": motivo,
        "omitidos_cerrados_desconocidos": omitidos_cerrados_desconocidos,
        "bytes_recibidos": bytes_recibidos,
    }
    logger.info("Plan 276 sync GitLab '%s': %s", project_name, resultado)
    return resultado


__all__ = ["sync_gitlab_tickets"]
