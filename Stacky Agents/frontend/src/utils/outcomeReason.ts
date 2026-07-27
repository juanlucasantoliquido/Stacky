// Plan 254 F4 — mapa puro `outcome_reason` → etiqueta + tono + acción sugerida.
//
// Por qué un módulo puro y no un test de render: `@testing-library/react` y
// `jsdom` NO están instalados en este repo, así que un test de vitest que
// renderice un componente React no es ejecutable acá. Los tests de UI de la casa
// prueban módulos `.ts` puros; el componente solo consume este mapa.
//
// Seis causas radicalmente distintas hoy colapsan al mismo "error" en la UI. El
// operador no puede distinguir "me quedé sin cuota" de "el código no compila", y
// son acciones OPUESTAS.

export type OutcomeTone = "exito" | "atencion" | "espera" | "error";

export interface OutcomeLabel {
  label: string;
  tone: OutcomeTone;
  /** Acción sugerida en una línea. Vacío = no hay nada que hacer. */
  action: string;
}

/** Los 9 de OUTCOME_REASONS (services/run_outcome.py), ni uno más ni uno menos. */
export const OUTCOME_REASON_LABELS: Record<string, OutcomeLabel> = {
  clean_exit: { label: "Terminó bien", tone: "exito", action: "" },
  dirty_exit_after_work: {
    label: "Entregó trabajo, cerró sucio",
    tone: "atencion",
    action: "Revisá el resultado: el trabajo está, el proceso cerró mal",
  },
  quota_exhausted: {
    label: "Se agotó la cuota del plan",
    tone: "espera",
    action: "Reintentá cuando se reponga la cuota",
  },
  stall_after_work: {
    label: "Quedó ocioso tras entregar",
    tone: "atencion",
    action: "Revisá el resultado",
  },
  stall_no_work: { label: "Se colgó sin entregar", tone: "error", action: "Reintentá" },
  preflight_blocked: {
    label: "Bloqueado antes de arrancar",
    tone: "error",
    action: "Mirá el chequeo que falló antes de arrancar",
  },
  reaper_timeout: {
    label: "Excedió el tiempo máximo",
    tone: "error",
    action: "Reintentá o subí el timeout",
  },
  reaper_heartbeat: { label: "Perdió señal de vida", tone: "error", action: "Reintentá" },
  cli_failure: {
    label: "Falló el runtime",
    tone: "error",
    action: "Mirá el detalle del error",
  },
};

/**
 * Etiqueta de un `outcome_reason`. Un reason futuro NO rompe la UI: se muestra
 * el string crudo con tono neutro de atención, nunca `undefined`.
 */
export function describeOutcomeReason(
  reason: string | null | undefined,
): OutcomeLabel | null {
  if (!reason) return null;
  const known = OUTCOME_REASON_LABELS[reason];
  if (known) return known;
  return { label: reason, tone: "atencion", action: "" };
}

export interface BlockedDowngrade {
  from?: string;
  to?: string;
  pending_review?: boolean;
  kind?: string;
}

/**
 * Plan 254 F1-bis — regla de honestidad NO negociable: un `completed`
 * preservado sobre un cierre sucio no puede presentarse como un éxito limpio.
 * Si esta marca no se muestra, el plan empeora el sistema.
 *
 * Acepta tanto el campo plano del payload (`dirty_close_pending_review`) como
 * el `blocked_downgrade` crudo del evento de estado.
 */
export function dirtyCloseNotice(source: {
  dirty_close_pending_review?: boolean;
  blocked_downgrade?: BlockedDowngrade | null;
} | null | undefined): string | null {
  if (!source) return null;
  const blocked = source.blocked_downgrade;
  const pending = source.dirty_close_pending_review === true || blocked?.pending_review === true;
  if (!pending) return null;
  const from = blocked?.from;
  const to = blocked?.to;
  const detalle = from && to ? ` (se quiso pasar de "${from}" a "${to}")` : "";
  return `Cierre sucio, estado preservado${detalle}. El trabajo figura como terminado pero el proceso cerró mal: revisalo.`;
}
