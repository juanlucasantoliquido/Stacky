"""
agenda_screens.py — Single source of truth for the Agenda Web screen catalogue.

Centralises the list of screens supported by the QA UAT pipeline so that
`uat_scenario_compiler`, `qa_uat_pipeline`, `ui_map_builder` and any future
component agree on:
  - which screen names are valid (case-sensitive, ASP.NET file naming),
  - how to detect a screen reference inside free-form Spanish text,
  - whether an arbitrary string maps to a known screen (case-insensitive).

Pre-Fase-1 each consumer kept its own hardcoded `frozenset({...})` literal,
which forced a 4-way edit every time the Agenda Web frontend grew a new page
and produced silent drift (the compiler accepted screens the pipeline had
never heard of). This module collapses the duplication.

PUBLIC API (stable):
  - `SUPPORTED_SCREENS`: frozenset[str] with the canonical filenames.
  - `is_supported(screen_name) -> bool`: case-insensitive membership check.
  - `extract_from_text(text) -> list[str]`: enumerate canonical screens
    mentioned anywhere in `text`, preserving deterministic order.

The full catalogue is sourced from `branches/NetCore/OnLine/AgendaWeb/` (main
screens) plus `branches/Materialize/OnLine/AgendaWeb/` (PopUps). Any addition
MUST be made here and nowhere else.
"""
from __future__ import annotations

from typing import Iterable

# ── Canonical catalogue ───────────────────────────────────────────────────────

# Screen filenames as the Agenda Web app serves them. Casing matters because
# the URL path is built by concatenating the base URL with this exact string
# (see `ui_map_builder.run` -> `url = base_url + "/" + screen`).
#
# Source: branches/NetCore/OnLine/AgendaWeb/ + branches/Materialize/OnLine/AgendaWeb/
# Maintained here as the single source of truth — do NOT duplicate this list
# elsewhere (compiler, pipeline, ui_map_builder all import from this module).
SUPPORTED_SCREENS: "frozenset[str]" = frozenset({
    # ── Pantallas principales ──────────────────────────────────────────────
    "FrmAgenda.aspx",
    "FrmDetalleLote.aspx",
    "FrmGestion.aspx",
    "FrmLogin.aspx",
    "Login.aspx",           # alias legacy (mantener para compatibilidad)

    # ── Búsqueda ──────────────────────────────────────────────────────────
    "FrmBusqueda.aspx",
    "FrmBusquedaJudicial.aspx",

    # ── Cliente ───────────────────────────────────────────────────────────
    "FrmDetalleClie.aspx",
    "FrmDetalleCliente.aspx",

    # ── Administración y configuración ────────────────────────────────────
    "FrmAdministrador.aspx",
    "FrmAdminEstrategias.aspx",
    "FrmParametros.aspx",
    "FrmFeriados.aspx",
    "FrmMonedas.aspx",
    "FrmOficinas.aspx",
    "FrmProductos.aspx",
    "FrmTablasGenerales.aspx",
    "FrmTablasGeneralesMandante.aspx",
    "FrmMandantes.aspx",
    "FrmSegmentacion.aspx",

    # ── Asignación y estrategias ──────────────────────────────────────────
    "FrmAsignarEstudio.aspx",
    "FrmAsignarLote.aspx",
    "FrmAsignarTipoDeJuicio.aspx",
    "FrmEstrategia.aspx",
    "FrmEdicionTars.aspx",
    "FrmVinculVariablesGMR.aspx",

    # ── Gestión de lotes ─────────────────────────────────────────────────
    "FrmGestionFlujos.aspx",
    "FrmGestionUsuarios.aspx",
    "FrmAvanzarFlow.aspx",

    # ── Agenda por tipo ───────────────────────────────────────────────────
    "FrmAgendaEquipo.aspx",
    "FrmAgendaJudicial.aspx",
    "FrmAgenteComisiones.aspx",

    # ── Judicial ──────────────────────────────────────────────────────────
    "FrmJDemanda.aspx",
    "FrmJEmbargo.aspx",
    "FrmJModificarDemanda.aspx",
    "FrmJReasignarAbogado.aspx",
    "FrmJConvenio.aspx",
    "FrmJConveniosAnulados.aspx",
    "FrmJElaborarDemanda.aspx",
    "FrmRadicarDemanda.aspx",
    "FrmValidacionGastosJudicial.aspx",

    # ── Liquidaciones y comisiones ────────────────────────────────────────
    "FrmLiquidaciones.aspx",
    "FrmLiquidarGastos.aspx",
    "FrmDetalleLiquidacion.aspx",
    "FrmLiquidComisiones.aspx",
    "FrmLiquidComisionesDet.aspx",
    "FrmLiquidComisionesProg.aspx",
    "FrmComisionistas.aspx",
    "FrmConfigComisiones.aspx",

    # ── Simulación ───────────────────────────────────────────────────────
    "FrmSimulacionUnitaria.aspx",
    "FrmSimulMasiva.aspx",

    # ── Reportes e informes ───────────────────────────────────────────────
    "FrmReportes.aspx",
    "FrmReporteOperativo.aspx",
    "FrmInformes.aspx",

    # ── Envíos y comunicaciones ───────────────────────────────────────────
    "FrmEnviarDocumentacion.aspx",
    "FrmMensajes.aspx",

    # ── Impresión ─────────────────────────────────────────────────────────
    "FrmImpConvenioJudicial.aspx",
    "FrmImpFichaClienteJudi.aspx",
    "FrmImpFichaClientePre.aspx",

    # ── Workflow ──────────────────────────────────────────────────────────
    "WorkflowFrame.aspx",
    "FrmEditorWorkflow.aspx",
    "FrmIframeWorkflow.aspx",
    "FrmEtapaVacia.aspx",

    # ── Misc ──────────────────────────────────────────────────────────────
    "Errors.aspx",
    "Default.aspx",
    "FrmBase.aspx",

    # ── PopUps (Materialize) ──────────────────────────────────────────────
    "PopAnCtaCte.aspx",
    "PopAnPrestamos.aspx",
    "PopAnTarjetas.aspx",
    "PopUpAgendar.aspx",
    "PopUpAgenteComisiones.aspx",
    "PopUpChequesProtestados.aspx",
    "PopUpCompromisos.aspx",
    "PopUpContactos.aspx",
    "PopUpContactosDomicilios.aspx",
    "PopUpContactosEmails.aspx",
    "PopUpContactosTelefonos.aspx",
    "PopUpControles.aspx",
    "PopUpConvenios.aspx",
    "PopUpConveniosVerTodos.aspx",
    "PopUpDetallePerfil.aspx",
    "PopUpDocumentosUpload.aspx",
    "PopUpDomicilios.aspx",
    "PopUpDomicMapa.aspx",
    "PopUpEmails.aspx",
    "PopUpEstadosEspeciales.aspx",
    "PopUpFlow.aspx",
    "PopUpGarantias.aspx",
    "PopUpGastosJudicial.aspx",
    "PopUpGestionesHistoricas.aspx",
    "PopUpJudiAgendar.aspx",
    "PopUpLiquidacionCaso.aspx",
    "PopUpLiquidacionPago.aspx",
    "PopUpNota.aspx",
    "PopUpNotasGestiones.aspx",
    "PopUpNotasGestionesJudicial.aspx",
    "PopUpPasajeJudicial.aspx",
    "PopUpRecomendaciones.aspx",
    "PopUpTelefonos.aspx",
})


# Pre-computed lowercase index for case-insensitive lookups. Built once at
# import time to avoid re-lowercasing the catalogue on every call.
_LOWER_INDEX: "dict[str, str]" = {s.lower(): s for s in SUPPORTED_SCREENS}


# ── Public API ────────────────────────────────────────────────────────────────

def is_supported(screen_name: str) -> bool:
    """Return True if `screen_name` matches a supported screen.

    The match is case-insensitive so that user-supplied scope hints like
    `frmagenda.aspx` or `FRMAGENDA.ASPX` resolve to the canonical
    `FrmAgenda.aspx`. Returns False for empty / non-string inputs instead of
    raising — callers are typically working with LLM output that may be
    malformed.
    """
    if not isinstance(screen_name, str) or not screen_name:
        return False
    return screen_name.lower() in _LOWER_INDEX


def extract_from_text(text: str) -> "list[str]":
    """Return canonical screen names mentioned in `text`, in catalogue order.

    Used by the pipeline orchestrator to decide which UI maps to build for a
    given ticket: it scans `plan_pruebas` titles + descriptions and pulls out
    every supported screen referenced. Detection is case-insensitive and
    substring-based (so `FrmAgenda.aspx` matches inside `Pantalla
    FrmAgenda.aspx — RF-003`).

    The output preserves a deterministic, sorted order so two consecutive
    pipeline runs against the same ticket build UI maps in the same sequence
    (helps when comparing evidence dirs).
    """
    if not isinstance(text, str) or not text:
        return []
    lower = text.lower()
    found = [canonical for low, canonical in _LOWER_INDEX.items() if low in lower]
    return sorted(found)


def normalize(screen_name: str) -> "str | None":
    """Return the canonical capitalisation of `screen_name`, or None.

    Convenience helper used by callers that accept user input (CLI flags,
    LLM-emitted JSON) and want to persist a single canonical form. Returns
    None for unsupported inputs so the caller can fail explicitly.
    """
    if not isinstance(screen_name, str) or not screen_name:
        return None
    return _LOWER_INDEX.get(screen_name.lower())


def add_discovered_screen(screen_name: str, from_exploration: "str | None" = None) -> bool:
    """Register a newly discovered screen in the runtime catalogue.

    This function DOES NOT modify the source file — it adds the screen only
    to the in-memory SUPPORTED_SCREENS and _LOWER_INDEX for the current
    process. Persisting permanently requires a human to edit the source list
    above (intentional: human review is required before promotion).

    Writes to ``cache/discovered_screens.json`` so the set survives between
    runs without touching the source code.  The JSON file is git-ignored (see
    cache/.gitignore) and is loaded automatically at the bottom of this module
    when it exists.

    Args:
        screen_name:       Canonical filename, e.g. ``FrmNewScreen.aspx``.
        from_exploration:  Optional path to exploration_report.json for provenance.

    Returns:
        True if the screen was added, False if it was already known.
    """
    import json as _json
    from pathlib import Path as _Path

    global SUPPORTED_SCREENS, _LOWER_INDEX  # noqa: PLW0603

    if not isinstance(screen_name, str) or not screen_name.endswith(".aspx"):
        raise ValueError(f"screen_name must be an .aspx filename, got {screen_name!r}")

    if screen_name.lower() in _LOWER_INDEX:
        return False  # already known

    # Add to in-memory catalogue
    SUPPORTED_SCREENS = SUPPORTED_SCREENS | frozenset({screen_name})
    _LOWER_INDEX[screen_name.lower()] = screen_name

    # Persist to cache/discovered_screens.json
    cache_dir = _Path(__file__).parent / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    disc_path = cache_dir / "discovered_screens.json"

    existing: dict = {}
    if disc_path.is_file():
        try:
            existing = _json.loads(disc_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    screens_list: list = existing.get("screens", [])
    if screen_name not in screens_list:
        screens_list.append(screen_name)

    existing["schema_version"] = "1.0"
    existing["screens"] = sorted(screens_list)
    existing["description"] = (
        "Screens discovered by autonomous_explorer.py and added via "
        "agenda_screens.add_discovered_screen(). Human review required before "
        "promoting to the static SUPPORTED_SCREENS list."
    )
    if from_exploration:
        provenance: dict = existing.get("provenance", {})
        provenance[screen_name] = str(from_exploration)
        existing["provenance"] = provenance

    disc_path.write_text(_json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


# ── Load discovered_screens at import time ────────────────────────────────────
# Screens added via add_discovered_screen() in previous runs are loaded here
# so the catalogue is complete without source-code changes.

def _load_discovered_screens() -> None:
    """Load cache/discovered_screens.json into SUPPORTED_SCREENS if present."""
    import json as _json
    from pathlib import Path as _Path

    global SUPPORTED_SCREENS, _LOWER_INDEX  # noqa: PLW0603

    disc_path = _Path(__file__).parent / "cache" / "discovered_screens.json"
    if not disc_path.is_file():
        return
    try:
        data = _json.loads(disc_path.read_text(encoding="utf-8"))
        for screen in data.get("screens", []):
            if isinstance(screen, str) and screen.lower() not in _LOWER_INDEX:
                SUPPORTED_SCREENS = SUPPORTED_SCREENS | frozenset({screen})
                _LOWER_INDEX[screen.lower()] = screen
    except Exception:
        pass  # Corrupt cache — ignore silently, static catalogue still works


_load_discovered_screens()


__all__ = [
    "SUPPORTED_SCREENS",
    "is_supported",
    "extract_from_text",
    "normalize",
    "add_discovered_screen",
]
