"""Plan 283 F5 - Dos fuentes, UN contrato. Las capas de arriba no saben de donde
vino la reunion.

D1 - el valor NO depende de Microsoft. `from_manual` funciona el dia 1, sin
credenciales, sin permisos de administrador y sin red. Graph es ADITIVO: si el
tenant del operador no lo permite, el modulo sigue entregando minutas y
pendientes. El operador pidio literalmente "pasarle U obtener": son dos caminos
detras del mismo contrato.

D7 - SIN polling, SIN daemon, SIN barrido. El sincronizado es on-demand: solo
cuando el operador aprieta "Actualizar" o abre la pantalla. No se registra
ningun hilo, ningun temporizador, ninguna funcion `_loop` y ningun post-hook.
Consecuencia buscada: las flags de lectura pueden nacer ON sin violar la
categoria (A) de la regla de flags (quemar recursos en reposo). Hay un gate por
AST que lo verifica (F5 caso 7).

Degradacion honesta: `list_upcoming` NUNCA lanza. Devuelve un `estado` distinto
de "ok" con un `detalle` accionable en castellano. Molde: `_probe_gitlab` de
`services/local_diagnostics.py`, que tiene CUATRO sub-veredictos por la misma
razon por la que este tiene TRES: un solo check da falso verde.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import config as _config
from services.graph_client import (
    GraphApiError,
    GraphClient,
    GraphConfigError,
    parse_iso_utc,
    resolve_graph_auth_path,
)


@dataclass(frozen=True)
class MeetingRecord:
    source: str                  # "manual" | "graph"
    external_id: str | None
    subject: str
    organizer: str | None
    started_at: datetime | None  # naive UTC SIEMPRE
    ended_at: datetime | None
    join_url: str | None


def _flag(nombre: str, default: bool) -> bool:
    return bool(getattr(_config.config, nombre, default))


def from_manual(
    *,
    subject: str,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    organizer: str | None = None,
) -> MeetingRecord:
    return MeetingRecord(
        source="manual",
        external_id=None,
        subject=(subject or "").strip() or "Reunion sin titulo",
        organizer=(organizer or None),
        started_at=started_at,
        ended_at=ended_at,
        join_url=None,
    )


def from_graph_event(event: dict) -> MeetingRecord:
    """Mapea un evento de calendario. NUNCA lanza por un campo que falte: un
    evento sin `onlineMeeting` es una reunion presencial, no un error."""
    evento = event or {}
    online = evento.get("onlineMeeting") or {}
    inicio = evento.get("start_at")
    fin = evento.get("end_at")
    if inicio is None:
        inicio = parse_iso_utc((evento.get("start") or {}).get("dateTime"))
    if fin is None:
        fin = parse_iso_utc((evento.get("end") or {}).get("dateTime"))
    organizador = (
        ((evento.get("organizer") or {}).get("emailAddress") or {}).get("name")
        or ((evento.get("organizer") or {}).get("emailAddress") or {}).get("address")
        or None
    )
    return MeetingRecord(
        source="graph",
        external_id=str(evento.get("id") or "") or None,
        subject=str(evento.get("subject") or "").strip() or "Reunion sin titulo",
        organizer=organizador,
        started_at=inicio,
        ended_at=fin,
        join_url=(online.get("joinUrl") or evento.get("onlineMeetingUrl") or None),
    )


def _credenciales(project: str) -> tuple[str, str]:
    tenant = str(getattr(_config.config, "STACKY_MEETINGS_GRAPH_TENANT", "") or "").strip()
    client_id = str(getattr(_config.config, "STACKY_MEETINGS_GRAPH_CLIENT_ID", "") or "").strip()
    return tenant, client_id


def crear_cliente(project: str, *, transport=None) -> GraphClient:
    """Fabrica del cliente. Es el SEAM: los tests inyectan `transport` o
    reemplazan esta funcion entera. No hace red."""
    tenant, client_id = _credenciales(project)
    return GraphClient(
        tenant=tenant,
        client_id=client_id,
        auth_path=resolve_graph_auth_path(project),
        transport=transport,
    )


def _apagado() -> dict | None:
    if not _flag("STACKY_MEETINGS_ENABLED", True):
        return {"estado": "apagado", "reuniones": [],
                "detalle": "La seccion Reuniones esta desactivada en la configuracion."}
    if not _flag("STACKY_MEETINGS_GRAPH_ENABLED", True):
        return {"estado": "apagado", "reuniones": [],
                "detalle": "La conexion con el calendario esta desactivada. "
                           "El camino manual sigue disponible."}
    return None


def list_upcoming(*, project: str, dias: int = 14, client: GraphClient | None = None) -> dict:
    """Reuniones proximas del calendario. NUNCA lanza.

    `client` es el seam de test: con un transporte falso se recorre todo el
    camino sin tocar la red.
    """
    apagada = _apagado()
    if apagada is not None:
        return apagada

    _tenant, client_id = _credenciales(project)
    if not client_id and client is None:
        return {
            "estado": "sin_credenciales", "reuniones": [],
            "detalle": (
                "Falta el identificador de la aplicacion registrada en Microsoft. "
                "Cargalo en la configuracion y despues hacé el ingreso una vez."
            ),
        }

    try:
        cliente = client if client is not None else crear_cliente(project)
        ahora = datetime.utcnow()
        eventos = cliente.list_events(desde=ahora - timedelta(days=1),
                                      hasta=ahora + timedelta(days=max(1, int(dias))))
    except GraphConfigError as exc:
        return {"estado": "sin_credenciales", "reuniones": [], "detalle": str(exc)}
    except GraphApiError as exc:
        if exc.kind == "auth":
            detalle = (
                "Microsoft rechazo la sesion guardada. Volvé a hacer el ingreso "
                "desde la pantalla de Reuniones."
            )
        elif exc.kind == "timeout":
            detalle = "Microsoft no respondio a tiempo. Probá de nuevo en un momento."
        elif exc.kind == "rate_limited":
            detalle = "Microsoft esta limitando los pedidos. Esperá un momento y reintentá."
        else:
            detalle = f"No se pudo leer el calendario ({exc.kind}): {exc}"
        return {"estado": "error", "reuniones": [], "detalle": detalle}
    except Exception as exc:  # noqa: BLE001 - nunca rompe la pantalla
        return {"estado": "error", "reuniones": [],
                "detalle": f"No se pudo leer el calendario: {exc}"}

    reuniones = [from_graph_event(e) for e in eventos]
    reuniones.sort(key=lambda r: (r.started_at is None, r.started_at or datetime.min))
    return {
        "estado": "ok",
        "reuniones": [
            {
                "source": r.source, "external_id": r.external_id, "subject": r.subject,
                "organizer": r.organizer,
                "started_at": r.started_at.isoformat() + "Z" if r.started_at else None,
                "ended_at": r.ended_at.isoformat() + "Z" if r.ended_at else None,
                "join_url": r.join_url,
            }
            for r in reuniones
        ],
        "detalle": f"{len(reuniones)} reuniones en los proximos {dias} dias.",
    }


def probe_graph(*, project: str, client: GraphClient | None = None) -> dict:
    """TRES sub-veredictos. Uno solo daria falso verde: tener el identificador
    cargado no prueba que la sesion sirva, y que la sesion sirva no prueba que
    el calendario se pueda leer. Molde: `local_diagnostics._probe_gitlab`."""
    detalle: dict = {"config": False, "auth": False, "calendario": False, "detalle": ""}
    apagada = _apagado()
    if apagada is not None:
        detalle["detalle"] = apagada["detalle"]
        return detalle

    _tenant, client_id = _credenciales(project)
    detalle["config"] = bool(client_id) or client is not None
    if not detalle["config"]:
        detalle["detalle"] = "Falta el identificador de la aplicacion registrada en Microsoft."
        return detalle

    try:
        cliente = client if client is not None else crear_cliente(project)
        cliente._access_token()
        detalle["auth"] = True
    except GraphConfigError as exc:
        detalle["detalle"] = str(exc)
        return detalle
    except Exception as exc:  # noqa: BLE001
        detalle["detalle"] = f"No se pudo renovar la sesion: {exc}"
        return detalle

    resultado = list_upcoming(project=project, dias=7, client=cliente)
    detalle["calendario"] = resultado["estado"] == "ok"
    detalle["detalle"] = resultado["detalle"]
    return detalle
