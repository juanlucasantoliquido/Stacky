"""Plan 270 F1 — A qué proveedor le corresponde escribir el estado de un ticket.

NO depende de STACKY_TICKETS_PROVIDER_ENABLED (Plan 70, default OFF en
config.py:1231-1233): esa flag gobierna la MIGRACIÓN masiva de call sites de
api/tickets.py, no la corrección de destino de una escritura puntual.

C5 — Una capa de services/ NUNCA importa de la capa web. Regla del repo escrita
en services/completion_sync.py:93-95: importar el módulo de endpoints de tickets
acopla service->web y arriesga un import circular al arrancar el daemon. El
cliente ADO se construye con services.project_context.build_ado_client(...), que
es el cuerpo literal del helper de api/tickets.py:358-367.

Este archivo tiene un centinela textual que prohíbe nombrar ese módulo con
notación de import, así que las referencias van siempre con barra (ruta), nunca
con punto.
"""
from __future__ import annotations

from dataclasses import dataclass

# Clave declarada en services/provider_capabilities.py:60.
CAPABILITY_UPDATE_STATE = "tracker.items.update_state"

# El texto NOMBRA la flag literal (C4): el operador tiene que poder actuar sin
# abrir el código.
GITLAB_FLAG_WORKAROUND = (
    "activá STACKY_GITLAB_ENABLED en Configuración > Arnés para que "
    "Stacky pueda escribir en GitLab; hasta entonces el estado hay que "
    "cambiarlo desde la issue."
)

_ADO_TRACKER_TYPES: frozenset[str] = frozenset({"", "azure_devops"})


@dataclass(frozen=True)
class StateWriter:
    tracker_type: str
    kind: str            # "provider" | "ado_client"
    handle: object       # TrackerProvider o AdoClient, según kind


def routing_enabled() -> bool:
    """STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED (default True)."""
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED", True))


def resolve_state_writer(ticket) -> StateWriter:
    """Devuelve el escritor correcto para `ticket`, o levanta.

    Plan 286 F2 — el tracker NO sale de la columna `ticket.tracker_type`, sale
    de `services.project_context.tracker_efectivo_de_ticket(ticket)`, que aplica
    la precedencia *columna explícita > config del proyecto > default*. Motivo:
    la columna tiene default `"azure_devops"` en el ORM (models.py:49), así que
    ese valor es indistinguible de "nadie la seteó" y MIENTE para todo ticket
    creado sin ese campo en un proyecto que no es Azure DevOps.

    - tracker efectivo "azure_devops" (o sin resolver) -> StateWriter(
      kind="ado_client") construido con
      services.project_context.build_ado_client(...).
    - tracker efectivo "gitlab" -> get_tracker_provider(stacky_project_name)
      (services/tracker_provider.py:125). Si esa fábrica levanta
      TrackerConfigError (p.ej. STACKY_GITLAB_ENABLED=false,
      config.py:1185-1186), se RE-LEVANTA como CapabilityUnavailable — NO se
      cae a ADO.
    - cualquier otro tracker efectivo -> CapabilityUnavailable.

    REGLA DURA: nunca devuelve kind == "ado_client" cuando el tracker efectivo
    no es "azure_devops" (ni cadena vacía/None).
    """
    from services.tracker_provider import CapabilityUnavailable, TrackerConfigError

    # Import local, como el resto del archivo (`:70`, `:78`, `:87`): no liga la
    # referencia al importar el módulo y sigue siendo interceptable.
    from services.project_context import tracker_efectivo_de_ticket

    ttype = tracker_efectivo_de_ticket(ticket)

    if ttype in _ADO_TRACKER_TYPES:
        # Importado como MÓDULO (no `from ... import build_ado_client`) para que
        # un monkeypatch sobre services.project_context.build_ado_client tenga
        # efecto, y para no ligar la referencia al importar este archivo.
        from services import project_context
        handle = project_context.build_ado_client(
            project_name=getattr(ticket, "stacky_project_name", None),
            tracker_project=getattr(ticket, "project", None),
            ticket=ticket,
        )
        return StateWriter(tracker_type="azure_devops", kind="ado_client", handle=handle)

    if ttype == "gitlab":
        from services import tracker_provider
        try:
            handle = tracker_provider.get_tracker_provider(
                getattr(ticket, "stacky_project_name", None)
            )
        except TrackerConfigError as exc:
            raise CapabilityUnavailable(
                CAPABILITY_UPDATE_STATE,
                "gitlab",
                reason=f"el proveedor GitLab no está disponible: {exc}",
                workaround=GITLAB_FLAG_WORKAROUND,
            ) from exc
        return StateWriter(tracker_type="gitlab", kind="provider", handle=handle)

    raise CapabilityUnavailable(
        CAPABILITY_UPDATE_STATE,
        ttype or "desconocido",
        reason=f"tracker '{ttype}' sin proveedor de escritura de estado",
    )


def _profile_for_ticket(ticket):
    """Perfil del cliente del ticket, o None. NUNCA levanta.

    Mismo patrón defensivo que el helper `_profile_for` de la bandeja, pero sin
    importar la capa web (C5).
    """
    try:
        from services.client_profile import load_client_profile
        name = getattr(ticket, "stacky_project_name", None)
        if not name:
            return None
        return load_client_profile(name)
    except Exception:  # noqa: BLE001
        return None


def _resolve_destination(ticket, requested_state: str):
    """(StateWriter, CloseTarget). Orden OBLIGATORIO: destino y DESPUÉS vocabulario.

    Invertirlo permitiría traducir a GitLab y escribir en Azure DevOps.
    """
    from services.close_intent import resolve_close_target
    from services.incident_inbox import resolve_closed_states

    profile = _profile_for_ticket(ticket)
    # C1 — resolve_closed_states() devuelve (estados, fuente): DOS elementos.
    # Pasarla entera haría que is_close_state() nunca reconozca "Done" y todo
    # cierre GitLab muera con unmappable_state.
    closed_states, _closed_source = resolve_closed_states(profile)

    writer = resolve_state_writer(ticket)          # F1 — destino
    target = resolve_close_target(                 # F0 — vocabulario
        writer.tracker_type, requested_state, closed_states,
    )
    return writer, target


def write_state_for_ticket(*, ticket, ado_id, requested_state: str) -> dict:
    """Resuelve destino (F1) + vocabulario (F0) y ejecuta la escritura.

    Devuelve {"tracker_type": str, "native_state": str, "closes": bool}.
    Levanta CapabilityUnavailable (destino imposible) o ValueError (estado no
    mapeable) — el caller las traduce a actions[].ok = False.
    """
    writer, target = _resolve_destination(ticket, requested_state)

    if writer.kind == "ado_client":
        writer.handle.update_work_item_state(int(ado_id), target.native_state)
    else:
        writer.handle.update_item_state(str(ado_id), target.native_state)

    return {
        "tracker_type": target.tracker_type,
        "native_state": target.native_state,
        "closes": target.closes,
    }


def preview_state_write(*, ticket, requested_state: str) -> dict:
    """Plan 270 F7 — Resuelve destino + vocabulario SIN escribir. Nunca levanta.

    Es write_state_for_ticket() menos la escritura: mismas dos llamadas
    (resolve_state_writer, resolve_close_target), mismo orden, cero I/O de
    escritura. Si algo falla, lo devuelve declarado en vez de propagarlo: el
    dry-run NUNCA puede tumbar el diálogo de cierre.

    Devuelve:
      {"resolved": True,  "tracker_type": str, "native_state": str,
       "closes": bool, "reason": "ok"}
      {"resolved": False, "tracker_type": str|None, "reason": str,
       "workaround": str}
    """
    from services.tracker_provider import CapabilityUnavailable

    # Plan 286 F2 — el dry-run le reportaba "azure_devops" al operador para un
    # ticket de un proyecto GitLab. Ahora reporta el tracker EFECTIVO.
    from services.project_context import tracker_efectivo_de_ticket

    ttype = tracker_efectivo_de_ticket(ticket)
    try:
        writer, target = _resolve_destination(ticket, requested_state)
    except CapabilityUnavailable as exc:
        return {
            "resolved": False,
            "tracker_type": ttype,
            "reason": exc.reason,
            "workaround": getattr(exc, "workaround", "") or "",
        }
    except ValueError as exc:
        return {
            "resolved": False,
            "tracker_type": ttype,
            "reason": str(exc),
            "workaround": "",
        }
    except Exception as exc:  # noqa: BLE001
        # El dry-run jamás devuelve 500 por culpa de esta fase.
        return {
            "resolved": False,
            "tracker_type": ttype,
            "reason": f"preview_error: {type(exc).__name__}",
            "workaround": "",
        }

    return {
        "resolved": True,
        "tracker_type": target.tracker_type,
        "native_state": target.native_state,
        "closes": target.closes,
        "reason": "ok",
    }
