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


__all__ = [
    "SUPPORTED_SCREENS",
    "is_supported",
    "extract_from_text",
    "normalize",
]
