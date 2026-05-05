"""
navigation_graph.py — Static navigation graph for Agenda Web.

Fase 2 of the QA UAT Agent free-form improvement plan.

Models Agenda Web as a directed graph of screens: nodes are screen filenames,
edges are labelled navigation actions (link, button, menu, popup_open, etc.).

The graph is used by `path_planner.py` to auto-compute `navigation_path[]`
inside intent_spec.json when the orchestrator only knows the entry screen and
the target screen (or goal action).

Design principles:
  - Static definition: no Playwright crawl at runtime. The graph is maintained
    here as the single source of truth for navigation topology.
  - Edge labels: each edge carries a human-readable `action` describing what
    the user does to traverse it (click menu item, click button, etc.).
  - PopUps are first-class nodes. They have edges FROM their parent screens
    and back (close / save).
  - Login is always the root: any path that doesn't already start at a
    post-login screen must go through FrmLogin.aspx first.

PUBLIC API:
  - `GRAPH`: dict[str, list[NavEdge]]  — adjacency list (source → edges)
  - `get_edges(screen) -> list[NavEdge]`: outgoing edges from a screen
  - `successors(screen) -> list[str]`: screens reachable in one step
  - `all_screens() -> frozenset[str]`: all nodes in the graph
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class NavEdge:
    """A directed edge in the navigation graph."""
    target: str           # destination screen (canonical filename)
    action: str           # human-readable navigation action
    label: str = ""       # optional UI label of the link/button clicked
    requires_login: bool = False   # True only for the Login→post-login edge
    is_popup: bool = False         # True when target is a PopUp


# ── Graph definition ─────────────────────────────────────────────────────────
#
# Convention:
#   - Edges represent the MINIMUM set of navigations to reach a screen.
#   - Only include edges that a test would actually traverse.
#   - PopUp edges are included because the compiler may generate scenarios
#     that open popups; the path planner needs to know they are reachable.
#
# Maintenance: add edges here when new screens are added to SUPPORTED_SCREENS
# in agenda_screens.py.

_RAW_GRAPH: dict[str, list[tuple]] = {

    # ── Login ────────────────────────────────────────────────────────────────
    "FrmLogin.aspx": [
        ("FrmAgenda.aspx",         "login_submit",     "Ingresar",        True,  False),
        ("FrmBusqueda.aspx",       "login_submit",     "Ingresar",        True,  False),
        ("Default.aspx",           "login_submit",     "Ingresar",        True,  False),
    ],
    "Login.aspx": [
        ("FrmLogin.aspx",          "redirect",         "",                False, False),
    ],

    # ── Home / Default ────────────────────────────────────────────────────────
    "Default.aspx": [
        ("FrmAgenda.aspx",         "menu_click",       "Agenda Personal", False, False),
        ("FrmBusqueda.aspx",       "menu_click",       "Búsqueda",        False, False),
        ("FrmAgendaEquipo.aspx",   "menu_click",       "Agenda Equipo",   False, False),
        ("FrmAgendaJudicial.aspx", "menu_click",       "Agenda Judicial", False, False),
        ("FrmReportes.aspx",       "menu_click",       "Reportes",        False, False),
        ("FrmAdministrador.aspx",  "menu_click",       "Administración",  False, False),
        ("FrmLiquidaciones.aspx",  "menu_click",       "Liquidaciones",   False, False),
    ],

    # ── Agenda Personal ───────────────────────────────────────────────────────
    "FrmAgenda.aspx": [
        ("FrmDetalleLote.aspx",    "row_click",        "abrir lote",      False, False),
        ("FrmDetalleClie.aspx",    "row_click",        "abrir cliente",   False, False),
        ("PopUpAgendar.aspx",      "button_click",     "Agendar",         False, True),
        ("PopUpNota.aspx",         "button_click",     "Nota",            False, True),
        ("Default.aspx",           "menu_click",       "Inicio",          False, False),
    ],

    # ── Búsqueda de clientes ──────────────────────────────────────────────────
    "FrmBusqueda.aspx": [
        ("FrmDetalleClie.aspx",    "row_click",        "abrir resultado", False, False),
        ("Default.aspx",           "menu_click",       "Inicio",          False, False),
    ],

    # ── Detalle de Cliente ────────────────────────────────────────────────────
    "FrmDetalleClie.aspx": [
        ("FrmDetalleLote.aspx",    "tab_click",        "Obligaciones",    False, False),
        ("FrmGestion.aspx",        "button_click",     "Gestionar",       False, False),
        ("PopUpAgendar.aspx",      "button_click",     "Agendar",         False, True),
        ("PopUpNota.aspx",         "button_click",     "Nota",            False, True),
        ("PopUpCompromisos.aspx",  "button_click",     "Compromisos",     False, True),
        ("PopUpContactos.aspx",    "button_click",     "Contactos",       False, True),
        ("PopUpConvenios.aspx",    "button_click",     "Convenios",       False, True),
        ("FrmBusqueda.aspx",       "back_button",      "Volver",          False, False),
    ],

    # ── Detalle de Lote ───────────────────────────────────────────────────────
    "FrmDetalleLote.aspx": [
        ("FrmGestion.aspx",        "button_click",     "Gestionar",       False, False),
        ("FrmDetalleClie.aspx",    "row_click",        "abrir cliente",   False, False),
        ("FrmAsignarLote.aspx",    "button_click",     "Asignar",         False, False),
        ("FrmAgenda.aspx",         "back_button",      "Volver",          False, False),
        ("PopUpAgendar.aspx",      "button_click",     "Agendar",         False, True),
        ("PopUpNota.aspx",         "button_click",     "Nota",            False, True),
    ],

    # ── Gestión ───────────────────────────────────────────────────────────────
    "FrmGestion.aspx": [
        ("FrmDetalleLote.aspx",    "back_button",      "Volver",          False, False),
        ("FrmDetalleClie.aspx",    "back_button",      "Volver",          False, False),
        ("PopUpAgendar.aspx",      "button_click",     "Agendar",         False, True),
        ("PopUpCompromisos.aspx",  "button_click",     "Compromisos",     False, True),
    ],

    # ── Agenda Equipo ─────────────────────────────────────────────────────────
    "FrmAgendaEquipo.aspx": [
        ("FrmDetalleClie.aspx",    "row_click",        "abrir cliente",   False, False),
        ("FrmDetalleLote.aspx",    "row_click",        "abrir lote",      False, False),
        ("Default.aspx",           "menu_click",       "Inicio",          False, False),
    ],

    # ── Agenda Judicial ───────────────────────────────────────────────────────
    "FrmAgendaJudicial.aspx": [
        ("FrmJDemanda.aspx",       "row_click",        "abrir demanda",   False, False),
        ("FrmJEmbargo.aspx",       "row_click",        "abrir embargo",   False, False),
        ("Default.aspx",           "menu_click",       "Inicio",          False, False),
        ("PopUpJudiAgendar.aspx",  "button_click",     "Agendar Judi",    False, True),
    ],

    # ── Judicial ──────────────────────────────────────────────────────────────
    "FrmJDemanda.aspx": [
        ("FrmAgendaJudicial.aspx", "back_button",      "Volver",          False, False),
        ("FrmJConvenio.aspx",      "button_click",     "Convenio",        False, False),
        ("PopUpPasajeJudicial.aspx","button_click",    "Pasaje",          False, True),
    ],
    "FrmJEmbargo.aspx": [
        ("FrmAgendaJudicial.aspx", "back_button",      "Volver",          False, False),
    ],
    "FrmJConvenio.aspx": [
        ("FrmJDemanda.aspx",       "back_button",      "Volver",          False, False),
    ],

    # ── Asignar Lote ─────────────────────────────────────────────────────────
    "FrmAsignarLote.aspx": [
        ("FrmDetalleLote.aspx",    "back_button",      "Volver",          False, False),
    ],

    # ── Administrador ─────────────────────────────────────────────────────────
    "FrmAdministrador.aspx": [
        ("FrmParametros.aspx",     "submenu_click",    "Parámetros",      False, False),
        ("FrmFeriados.aspx",       "submenu_click",    "Feriados",        False, False),
        ("FrmTablasGenerales.aspx","submenu_click",    "Tablas Generales",False, False),
        ("Default.aspx",           "menu_click",       "Inicio",          False, False),
    ],
    "FrmParametros.aspx": [
        ("FrmAdministrador.aspx",  "back_button",      "Volver",          False, False),
    ],
    "FrmFeriados.aspx": [
        ("FrmAdministrador.aspx",  "back_button",      "Volver",          False, False),
    ],
    "FrmTablasGenerales.aspx": [
        ("FrmAdministrador.aspx",  "back_button",      "Volver",          False, False),
    ],

    # ── Reportes ─────────────────────────────────────────────────────────────
    "FrmReportes.aspx": [
        ("Default.aspx",           "menu_click",       "Inicio",          False, False),
    ],

    # ── Liquidaciones ────────────────────────────────────────────────────────
    "FrmLiquidaciones.aspx": [
        ("FrmDetalleLiquidacion.aspx", "row_click",    "abrir liquidación",False, False),
        ("Default.aspx",           "menu_click",       "Inicio",          False, False),
    ],
    "FrmDetalleLiquidacion.aspx": [
        ("FrmLiquidaciones.aspx",  "back_button",      "Volver",          False, False),
    ],

    # ── Simulación ───────────────────────────────────────────────────────────
    "FrmSimulacionUnitaria.aspx": [
        ("Default.aspx",           "menu_click",       "Inicio",          False, False),
    ],

    # ── PopUps ────────────────────────────────────────────────────────────────
    # PopUps close back to their parent. We model the "save + close" action as
    # returning to the opener; the path planner uses these edges to know that
    # after interacting with the popup, the user ends up on the parent.
    "PopUpAgendar.aspx": [
        ("FrmAgenda.aspx",         "popup_close",      "Cerrar/Guardar",  False, False),
        ("FrmDetalleClie.aspx",    "popup_close",      "Cerrar/Guardar",  False, False),
        ("FrmDetalleLote.aspx",    "popup_close",      "Cerrar/Guardar",  False, False),
        ("FrmGestion.aspx",        "popup_close",      "Cerrar/Guardar",  False, False),
    ],
    "PopUpNota.aspx": [
        ("FrmAgenda.aspx",         "popup_close",      "Cerrar/Guardar",  False, False),
        ("FrmDetalleClie.aspx",    "popup_close",      "Cerrar/Guardar",  False, False),
    ],
    "PopUpCompromisos.aspx": [
        ("FrmDetalleClie.aspx",    "popup_close",      "Cerrar/Guardar",  False, False),
        ("FrmGestion.aspx",        "popup_close",      "Cerrar/Guardar",  False, False),
    ],
    "PopUpContactos.aspx": [
        ("FrmDetalleClie.aspx",    "popup_close",      "Cerrar",          False, False),
    ],
    "PopUpConvenios.aspx": [
        ("FrmDetalleClie.aspx",    "popup_close",      "Cerrar",          False, False),
    ],
    "PopUpJudiAgendar.aspx": [
        ("FrmAgendaJudicial.aspx", "popup_close",      "Cerrar/Guardar",  False, False),
    ],
    "PopUpPasajeJudicial.aspx": [
        ("FrmJDemanda.aspx",       "popup_close",      "Cerrar",          False, False),
    ],
}

# Compile to NavEdge objects
GRAPH: dict[str, list[NavEdge]] = {
    src: [NavEdge(target=e[0], action=e[1], label=e[2],
                  requires_login=e[3], is_popup=e[4])
          for e in edges]
    for src, edges in _RAW_GRAPH.items()
}

# ── Goal-action → target-screen mapping ──────────────────────────────────────
#
# Maps common Spanish goal_action labels (from intent_spec.goal_action) to the
# primary screen where that action takes place. Used by path_planner to auto-
# detect which screen the user is trying to reach.

GOAL_ACTION_TARGETS: dict[str, str] = {
    # Agenda / agendar
    "agendar_contacto":          "PopUpAgendar.aspx",
    "agendar":                   "PopUpAgendar.aspx",
    "crear_agenda":              "PopUpAgendar.aspx",
    "nueva_agenda":              "PopUpAgendar.aspx",

    # Búsqueda de cliente
    "buscar_cliente":            "FrmBusqueda.aspx",
    "busqueda_cliente":          "FrmBusqueda.aspx",
    "search_cliente":            "FrmBusqueda.aspx",

    # Detalle de cliente
    "ver_detalle_cliente":       "FrmDetalleClie.aspx",
    "detalle_cliente":           "FrmDetalleClie.aspx",

    # Compromisos de pago
    "crear_compromiso_pago":     "PopUpCompromisos.aspx",
    "compromiso_pago":           "PopUpCompromisos.aspx",
    "nuevo_compromiso":          "PopUpCompromisos.aspx",

    # Notas / observaciones
    "crear_nota":                "PopUpNota.aspx",
    "agregar_nota":              "PopUpNota.aspx",
    "nota_gestion":              "PopUpNota.aspx",

    # Gestión
    "registrar_gestion":         "FrmGestion.aspx",
    "nueva_gestion":             "FrmGestion.aspx",
    "gestionar":                 "FrmGestion.aspx",

    # Detalle de lote
    "ver_lote":                  "FrmDetalleLote.aspx",
    "detalle_lote":              "FrmDetalleLote.aspx",
    "abrir_lote":                "FrmDetalleLote.aspx",

    # Agenda judicial
    "agenda_judicial":           "FrmAgendaJudicial.aspx",
    "agendar_judicial":          "PopUpJudiAgendar.aspx",
    "ver_demanda":               "FrmJDemanda.aspx",
    "ver_embargo":               "FrmJEmbargo.aspx",
    "crear_convenio_judicial":   "FrmJConvenio.aspx",

    # Liquidaciones
    "ver_liquidaciones":         "FrmLiquidaciones.aspx",
    "liquidar":                  "FrmLiquidaciones.aspx",

    # Simulación
    "simular":                   "FrmSimulacionUnitaria.aspx",
    "simulacion_unitaria":       "FrmSimulacionUnitaria.aspx",

    # Reportes
    "ver_reportes":              "FrmReportes.aspx",
    "reporte":                   "FrmReportes.aspx",

    # Contactos
    "ver_contactos":             "PopUpContactos.aspx",
    "editar_contactos":          "PopUpContactos.aspx",

    # Convenios
    "ver_convenios":             "PopUpConvenios.aspx",
    "crear_convenio":            "PopUpConvenios.aspx",

    # Administración
    "administrar":               "FrmAdministrador.aspx",
    "parametros":                "FrmParametros.aspx",
    "ver_feriados":              "FrmFeriados.aspx",
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_edges(screen: str) -> list[NavEdge]:
    """Return outgoing edges from `screen`, or [] if unknown."""
    return GRAPH.get(screen, [])


def successors(screen: str) -> list[str]:
    """Return list of screens reachable in one step from `screen`."""
    return [e.target for e in get_edges(screen)]


def all_screens() -> frozenset[str]:
    """Return all nodes (source screens) defined in the graph."""
    return frozenset(GRAPH.keys())


def target_for_goal(goal_action: str) -> str | None:
    """Return the primary target screen for a goal_action label, or None."""
    if not goal_action:
        return None
    # Exact match first
    if goal_action in GOAL_ACTION_TARGETS:
        return GOAL_ACTION_TARGETS[goal_action]
    # Substring fuzzy match (e.g. "crear_un_compromiso" → compromiso_pago)
    lower = goal_action.lower()
    for key, screen in GOAL_ACTION_TARGETS.items():
        if key in lower or lower in key:
            return screen
    return None
