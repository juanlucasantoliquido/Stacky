// frontend/src/utils/finalStateOutcome.ts
// Plan 271 F6 — mapa puro `final_state_outcome.reason` → etiqueta + tono + acción.
// El catálogo canónico vive en backend/services/final_state_resolver.py
// (ALL_FINAL_STATE_REASONS). `test_plan271_reason_catalog.py` verifica que este
// archivo cubra TODAS las razones de ese conjunto: agregar una allá sin agregarla
// acá deja el test rojo. NO cambies las keys sin cambiar el conjunto de Python.
//
// Por qué un módulo `.ts` puro y no un test de render: `@testing-library/react`
// y `jsdom` NO están instalados en este repo. Mismo razonamiento que
// `frontend/src/utils/outcomeReason.ts` (plan 254).

export type FinalStateTone = "exito" | "atencion" | "espera" | "error";

export interface FinalStateLabel {
  label: string;
  tone: FinalStateTone;
  action: string;
}

export interface FinalStateOutcome {
  applied?: boolean;
  to?: string | null;
  source?: string;
  reason?: string;
  at?: string;
}

export const FINAL_STATE_REASON_LABELS: Record<string, FinalStateLabel> = {
  // ── se movió ────────────────────────────────────────────────────────────
  ok: { label: "Movida al estado configurado", tone: "exito", action: "" },
  already_in_state: { label: "Ya estaba en ese estado", tone: "exito", action: "" },
  // ── falta configurar (acción del operador) ──────────────────────────────
  no_config: {
    label: "Nadie configuró a qué estado mover",
    tone: "atencion",
    action: "Configuralo en Ajustes → Estados, en la tarjeta del rol",
  },
  no_final_state: {
    label: "El rol no tiene estado de salida",
    tone: "atencion",
    action: "Elegí 'Al terminar OK, mover a' en Ajustes → Estados",
  },
  no_matrix_cell: {
    label: "Sin regla para este tipo de incidencia",
    tone: "atencion",
    action: "Configuralo en Ajustes → Estados, en la tarjeta del rol",
  },
  not_requested: {
    label: "Sin estado destino para este cierre",
    tone: "atencion",
    action: "Configuralo en Ajustes → Estados",
  },
  state_not_applicable: {
    label: "El estado configurado no aplica a este rol",
    tone: "atencion",
    action: "Revisá los estados del rol en Ajustes → Estados",
  },
  flag_off: {
    label: "El movimiento automático está apagado",
    tone: "atencion",
    action: "Prendé 'estado final del empleado' en Ajustes → Arnés",
  },
  no_project_context: {
    label: "Se movió, pero sin saber a qué tablero pertenece",
    tone: "atencion",
    action: "Revisá que la incidencia esté vinculada a un proyecto de Stacky",
  },
  // ── decisión humana / espera (no hay nada que arreglar) ─────────────────
  review_mode_hold: {
    label: "En espera de tu revisión",
    tone: "espera",
    action: "Aprobá la publicación para que se mueva",
  },
  human_moved_out_of_flow: {
    label: "La moviste vos: Stacky no la pisó",
    tone: "espera",
    action: "",
  },
  not_ok_status: {
    label: "No terminó bien: no se movió",
    tone: "espera",
    action: "Revisá el resultado antes de moverla",
  },
  dev_build_gate_no_state: {
    label: "Sin compilación verde reciente: no se movió",
    tone: "espera",
    action: "Corré el build y volvé a intentar",
  },
  already_written_by_other_engine: {
    label: "Ya la había movido otro paso del cierre",
    tone: "espera",
    action: "",
  },
  // ── error operable ──────────────────────────────────────────────────────
  publish_not_ok: {
    label: "No se publicó el comentario: no se movió",
    tone: "error",
    action: "Mirá el error de publicación y reintentá",
  },
  transition_failed: {
    label: "El tablero rechazó el cambio de estado",
    tone: "error",
    action: "Mirá el detalle del error y verificá que el estado exista en el tablero",
  },
  no_ado_id: {
    label: "La incidencia no tiene id en el tablero",
    tone: "error",
    action: "Vinculala al tablero",
  },
  no_ado_id_or_stacky_project: {
    label: "Falta el id en el tablero o el proyecto",
    tone: "error",
    action: "Revisá que la incidencia esté vinculada a un proyecto",
  },
  no_ticket: {
    label: "No se encontró la incidencia",
    tone: "error",
    action: "Refrescá el tablero",
  },
  no_ticket_id: {
    label: "La ejecución no está atada a una incidencia",
    tone: "error",
    action: "Revisá cómo se lanzó el empleado",
  },
  ticket_lookup_failed: {
    label: "No se pudo leer la incidencia",
    tone: "error",
    action: "Reintentá el cierre",
  },
  no_agent_type: {
    label: "No se pudo saber qué rol terminó",
    tone: "error",
    action: "Revisá el empleado asignado a la incidencia",
  },
  no_target_or_id: {
    label: "Faltó el estado destino o el id",
    tone: "error",
    action: "Configuralo en Ajustes → Estados",
  },
  // ── conexión con el tablero ─────────────────────────────────────────────
  provider_unavailable: {
    label: "No se pudo hablar con el tablero",
    tone: "error",
    action: "Revisá la conexión del tablero en Ajustes",
  },
  no_provider: {
    label: "Sin conexión configurada al tablero",
    tone: "error",
    action: "Configurá la conexión en Ajustes",
  },
  ado_client_unavailable: {
    label: "Falta el conector del tablero",
    tone: "error",
    action: "Revisá la instalación",
  },
  exception: {
    label: "Error inesperado al mover la incidencia",
    tone: "error",
    action: "Mirá el detalle de la ejecución",
  },
};

/** Un reason futuro NO rompe la UI: string crudo, tono neutro, nunca `undefined`. */
export function describeFinalState(
  o: FinalStateOutcome | null | undefined,
): FinalStateLabel | null {
  if (!o || !o.reason) return null;
  const known = FINAL_STATE_REASON_LABELS[o.reason];
  if (known) {
    if (o.reason === "ok" && o.to) return { ...known, label: `Movida a "${o.to}"` };
    return known;
  }
  return { label: o.reason, tone: "atencion", action: "" };
}
