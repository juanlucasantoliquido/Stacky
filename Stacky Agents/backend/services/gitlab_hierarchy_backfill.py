"""services/gitlab_hierarchy_backfill.py — Plan 277 F5.

Publica en el GitLab del operador, como etiquetas reales, la clasificación que él
hizo dentro de Stacky. Es la ÚNICA ruta de este plan que escribe en su sistema.

DOS FUNCIONES, Y LA SEPARACIÓN ES EL PUNTO:
  · `planificar_backfill`  READ-ONLY. Arma el diff: qué se le agregaría a qué issue.
    Cero escrituras, y por eso NO lleva flag: ver una comparación no puede necesitar
    permiso. Es la partición ON/OFF del precedente `STACKY_PIPELINE_NL_EDIT_ENABLED`
    (ver el diff) / `..._COMMIT_ENABLED` (empujarlo de verdad).
  · `ejecutar_backfill`    ESCRIBE. Un PUT por issue, SOLO sobre los ítems que el
    operador nombró uno por uno, y gateado por
    `STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED`, que nace APAGADA.

SOLO SE AGREGA, NUNCA SE REEMPLAZA NI SE QUITA. La API de GitLab acepta tres formas
de tocar las etiquetas de un issue: `add_labels` (agrega), `remove_labels` (quita) y
la que manda el juego completo, que REEMPLAZA todo lo que el issue tenía. Esa última
borraría en silencio las etiquetas que el operador puso a mano —prioridades, equipos,
lo que sea— sobre issues que Stacky no creó, y no hay forma de recuperarlas. Este
módulo emite `add_labels` y nada más; hay un criterio de aceptación del plan que
verifica, por texto, que la clave destructiva no aparece ni una vez acá adentro.

GITLAB MANDA (§3.2). Un issue cuyo `type::` remoto DIFIERE de la clasificación local
se marca `conflicto=True`, NO entra en `agregar` y se rechaza aunque venga en la lista
del operador: se lista en el diff para que él lo vea y lo decida a mano en GitLab.

UN SOLO MOTOR. Este módulo no parsea etiquetas: le pregunta al contrato
(`services/gitlab_hierarchy.py`) qué dice el issue y qué etiqueta corresponde escribir.
Comparar `type::...` con un `startswith` propio acá sería el motor nº 5, que es
exactamente la enfermedad que el plan 277 existe para curar.
"""
from __future__ import annotations

import logging
from typing import Optional

import config  # importado a nivel módulo para poder parchear en tests
from db import session_scope
from models import Ticket
from services.gitlab_hierarchy import (
    etiqueta_de_padre,
    etiqueta_de_tipo,
    normalizar_token,
)
from services.project_context import resolve_project_context

logger = logging.getLogger(__name__)

FLAG_ESCRITURA = "STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED"
_TRACKER = "gitlab"


def escritura_habilitada() -> bool:
    """Plan 277 F5 — flag default OFF (excepcion B). `config` es el MÓDULO."""
    return bool(getattr(config.config, FLAG_ESCRITURA, False))


def _es_gitlab(ctx) -> bool:
    return (getattr(ctx, "tracker_type", "") or "").strip().lower() == _TRACKER


def _proveedor(project_name: str, provider=None):
    """El proveedor del tracker. Punto ÚNICO de construcción: los tests lo reemplazan
    acá para probar que hay caminos donde no se construye ninguno."""
    if provider is not None:
        return provider
    from services.tracker_provider import get_tracker_provider  # noqa: PLC0415

    return get_tracker_provider(project_name)


def _plan_vacio(project_name: str) -> dict:
    return {"proyecto": project_name, "total": 0, "cambios": [], "con_conflicto": 0}


def _candidatas(ctx) -> list[dict]:
    """Los tickets que TIENEN clasificación local para publicar, como datos planos.

    La lectura de la BD se cierra ANTES de la primera llamada HTTP: sostener una
    sesión de sqlite abierta durante N requests contra el GitLab de la empresa es la
    receta del `database table is locked` que ya conoce este repo.

    El filtro va por `stacky_project_name` EXACTO y `tracker_type` gitlab, y no por el
    `or_` laxo de `api/tickets.py:348-355`: acá se decide sobre qué sistema externo se
    escribe, y ahí no se adivina.
    """
    with session_scope() as session:
        filas = (
            session.query(Ticket)
            .filter(
                Ticket.stacky_project_name == ctx.stacky_project_name,
                Ticket.tracker_type == _TRACKER,
            )
            .order_by(Ticket.ado_id)
            .all()
        )
        return [
            {
                "ado_id": f.ado_id,
                "title": f.title or "",
                "url": f.ado_url or "",
                "local_work_item_type": f.local_work_item_type,
                "local_parent_iid": f.local_parent_iid,
            }
            for f in filas
            if f.ado_id and (f.local_work_item_type or f.local_parent_iid)
        ]


def _deseadas(candidata: dict) -> list[str]:
    """Las etiquetas que la clasificación local del operador querría publicar.

    Se componen con el contrato (`etiqueta_de_tipo` / `etiqueta_de_padre`), que es el
    mismo que las va a volver a leer. Componerlas acá a mano produciría etiquetas que
    Stacky escribe y después no sabe interpretar — el bug que F1 cerró.
    """
    etiquetas: list[str] = []
    tipo = candidata.get("local_work_item_type")
    if tipo:
        etiquetas.append(etiqueta_de_tipo(tipo))
    padre = candidata.get("local_parent_iid")
    if padre:
        try:
            etiquetas.append(etiqueta_de_padre(padre))
        except ValueError as exc:
            logger.warning(
                "Plan 277 F5: el ticket %s tiene un padre local inutilizable (%s); se "
                "publica solo el tipo.", candidata.get("ado_id"), exc,
            )
    return etiquetas


def _veredicto_remoto(item: dict) -> tuple[list[str], Optional[str], Optional[int]]:
    """Lo que el CONTRATO ve HOY en el issue, reconstruido desde su propio veredicto.

    Devuelve `(ya_tiene, tipo_remoto, padre_remoto)`. `tipo_remoto` es None cuando el
    tipo no salió de una etiqueta: el default de GitLab y el campo nativo NO son una
    afirmación del operador y no pueden generar un conflicto (§3.2, regla del contrato).
    """
    ya_tiene: list[str] = []
    tipo_remoto = None
    if (item.get("origen_tipo") or "") == "label":
        tipo_remoto = item.get("work_item_type")
        ya_tiene.append(etiqueta_de_tipo(tipo_remoto))
    padre_remoto = item.get("parent")
    if padre_remoto:
        try:
            ya_tiene.append(etiqueta_de_padre(padre_remoto))
        except ValueError:
            padre_remoto = None
    return ya_tiene, tipo_remoto, padre_remoto


def _hay_conflicto(candidata: dict, tipo_remoto, padre_remoto) -> bool:
    """GitLab manda: si ya dice algo DISTINTO, Stacky no lo pisa ni lo discute."""
    tipo_local = candidata.get("local_work_item_type")
    if tipo_remoto and tipo_local and normalizar_token(tipo_remoto) != normalizar_token(tipo_local):
        return True
    padre_local = candidata.get("local_parent_iid")
    if padre_remoto and padre_local and int(padre_remoto) != int(padre_local):
        return True
    return False


def planificar_backfill(project_name: str, *, provider=None) -> dict:
    """READ-ONLY. Devuelve el diff: qué etiquetas se agregarían a qué issues.

    NO hace ninguna escritura. Returns:
      {"proyecto": str, "total": int,
       "cambios": [{"ado_id": int, "iid": int, "title": str, "url": str,
                    "agregar": ["type::epic", "epic::42"],
                    "ya_tiene": ["type::bug"],          # conflicto: GitLab dice otra cosa
                    "conflicto": bool}],
       "con_conflicto": int}

    Un issue cuyo `type::` remoto DIFIERE de la clasificación local se marca
    `conflicto=True` y NO entra en `agregar` (§3.2: GitLab manda). Se lista para que el
    operador lo vea y decida a mano en GitLab.

    `provider` es ADITIVO respecto de la firma del plan (`planificar_backfill(nombre)`
    sigue siendo válida) y existe por la misma razón que en `sync_gitlab_tickets`: sin
    él, probar que esta función no escribe exigiría parchear un global.

    SI NO SE PUDO LEER el estado remoto de un issue, ese issue se marca en conflicto
    con su `error`: no verificar qué tiene GitLab y escribir igual es exactamente el
    riesgo que este módulo no puede correr.
    """
    ctx = resolve_project_context(project_name)
    if ctx is None or not _es_gitlab(ctx):
        # BACKWARD-COMPAT: un proyecto ADO sale por acá sin construir NADA.
        return _plan_vacio(project_name)

    candidatas = _candidatas(ctx)
    if not candidatas:
        return _plan_vacio(project_name)

    prov = _proveedor(project_name, provider)
    cambios: list[dict] = []
    for candidata in candidatas:
        ado_id = int(candidata["ado_id"])
        entrada = {
            "ado_id": ado_id,
            "iid": ado_id,          # en GitLab, `ado_id` LLEVA el iid del proyecto
            "title": candidata["title"],
            "url": candidata["url"],
            "agregar": [],
            "ya_tiene": [],
            "conflicto": False,
        }
        try:
            item = prov.get_item(str(ado_id))
        except Exception as exc:
            entrada["conflicto"] = True
            entrada["error"] = str(exc)
            logger.warning(
                "Plan 277 F5: no se pudo leer el issue %s para armar el diff: %s",
                ado_id, exc,
            )
            cambios.append(entrada)
            continue

        # El diff describe el objeto REMOTO —es sobre él que se va a escribir—, así que
        # el título y la URL salen del issue recién leído y no de la copia local, que
        # puede estar vieja. La fila de la BD queda de respaldo si el issue no los trae.
        entrada["title"] = item.get("title") or candidata["title"]
        entrada["url"] = item.get("web_url") or candidata["url"]

        ya_tiene, tipo_remoto, padre_remoto = _veredicto_remoto(item)
        entrada["ya_tiene"] = ya_tiene
        entrada["conflicto"] = _hay_conflicto(candidata, tipo_remoto, padre_remoto)
        if not entrada["conflicto"]:
            entrada["agregar"] = [e for e in _deseadas(candidata) if e not in ya_tiene]
        cambios.append(entrada)

    return {
        "proyecto": project_name,
        "total": len(cambios),
        "cambios": cambios,
        "con_conflicto": sum(1 for c in cambios if c["conflicto"]),
    }


def _escribir_etiquetas(prov, iid: int, etiquetas: list[str]) -> None:
    """EL ÚNICO punto de escritura del módulo. Un PUT, aditivo, contra un issue.

    `add_labels` agrega al juego que el issue ya tiene y deja intacto todo lo demás.
    La otra clave —la que manda el juego completo— lo REEMPLAZA: borraría las
    etiquetas que el operador puso a mano, sin aviso y sin vuelta atrás. Por eso no
    aparece en este archivo ni una vez, y `remove_labels` tampoco.
    """
    cliente = getattr(prov, "_client", None)
    if cliente is None:
        raise RuntimeError(
            "El proveedor de GitLab no expone un cliente HTTP usable; no se escribe nada."
        )
    ruta = f"/projects/{cliente._project_path()}/issues/{iid}"
    cliente._request("PUT", ruta, json_body={"add_labels": ",".join(etiquetas)})


def ejecutar_backfill(project_name: str, ado_ids: list, *, provider=None) -> dict:
    """ESCRIBE EN EL GITLAB DEL OPERADOR. Un PUT `add_labels` por issue.

    - Solo los `ado_ids` que el operador mandó EXPLÍCITAMENTE. Nunca "todos".
      Una lista vacía devuelve {"escritos": 0} sin tocar nada.
    - Solo AGREGA etiquetas (`add_labels`). Nunca quita, nunca reemplaza el juego
      entero (ver `_escribir_etiquetas`).
    - Los `ado_ids` con `conflicto=True` se rechazan aunque vengan en la lista.
    - Corta ante el primer fallo, devuelve lo escrito y lo pendiente, y no reintenta.
    Returns: {"escritos": int, "omitidos": int, "fallidos": [{"ado_id","error"}],
              "pendientes": [int]}

    EL KILL-SWITCH SE COMPRUEBA DOS VECES, acá y en el endpoint que responde 403. No
    es redundancia decorativa: el endpoint protege al operador (le explica qué encender)
    y este guard protege su GitLab de cualquier llamador futuro que no exista todavía.
    Con la flag apagada devuelve la misma forma más `flag_off: True`, y cero requests.
    """
    pedidos: list[int] = []
    for crudo in (ado_ids or []):
        try:
            valor = int(str(crudo).strip())
        except (TypeError, ValueError):
            logger.warning("Plan 277 F5: se ignora un identificador no numérico: %r", crudo)
            continue
        if valor not in pedidos:
            pedidos.append(valor)

    base = {"escritos": 0, "omitidos": 0, "fallidos": [], "pendientes": []}
    if not escritura_habilitada():
        logger.info(
            "Plan 277 F5: publicación de etiquetas pedida con %s apagada; no se escribe nada.",
            FLAG_ESCRITURA,
        )
        return {**base, "omitidos": len(pedidos), "flag_off": True}
    if not pedidos:
        return base

    prov = _proveedor(project_name, provider)
    plan = planificar_backfill(project_name, provider=prov)
    por_id = {c["ado_id"]: c for c in plan["cambios"]}

    escritos = omitidos = 0
    fallidos: list[dict] = []
    pendientes: list[int] = []

    for posicion, ado_id in enumerate(pedidos):
        cambio = por_id.get(ado_id)
        if cambio is None or cambio["conflicto"] or not cambio["agregar"]:
            # No pertenece al proyecto, o GitLab ya dice otra cosa, o no hay nada que
            # agregar (segunda corrida): las tres son "no se toca", no un error.
            omitidos += 1
            continue
        try:
            _escribir_etiquetas(prov, cambio["iid"], cambio["agregar"])
        except Exception as exc:
            # CORTE DURO. Lo que sigue queda PENDIENTE, no fallido: no se sabe si
            # habría andado, y reintentar a ciegas contra el sistema de la empresa
            # después de un fallo que no se entiende es peor que parar.
            fallidos.append({"ado_id": ado_id, "error": str(exc)})
            pendientes = pedidos[posicion + 1:]
            logger.warning(
                "Plan 277 F5: falló el issue %s (%s); se corta y quedan %d pendientes.",
                ado_id, exc, len(pendientes),
            )
            break
        escritos += 1

    resultado = {
        "escritos": escritos,
        "omitidos": omitidos,
        "fallidos": fallidos,
        "pendientes": pendientes,
    }
    logger.info("Plan 277 F5 backfill '%s': %s", project_name, resultado)
    return resultado


__all__ = ["planificar_backfill", "ejecutar_backfill", "escritura_habilitada", "FLAG_ESCRITURA"]
