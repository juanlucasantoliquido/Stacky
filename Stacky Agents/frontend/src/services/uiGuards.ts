/**
 * Plan 136 — Guards puros de UI: protección de trabajo y acciones seguras.
 * Módulo SIN dependencias (ni React, ni zustand, ni endpoints) para ser
 * testeable con vitest puro, sin jsdom. Cada función es determinista.
 */

export interface BackdropGuardInput {
  /** Hay contenido tipeado / cambios sin guardar en el modal. */
  dirty: boolean;
  /** Hay una mutación o lanzamiento en vuelo. */
  busy: boolean;
}

/** Regla compartida F2: el click en backdrop solo cierra un modal pristine y ocioso.
 *  Los botones Cancelar/✕ NO pasan por acá: cierran siempre. */
export function shouldCloseOnBackdrop(input: BackdropGuardInput): boolean {
  return !input.dirty && !input.busy;
}

export interface CanGenerateEpicInput {
  step: string;               // Step del modal ("brief" | "running" | ...)
  briefEmpty: boolean;        // brief.trim().length === 0
  isLaunching: boolean;       // POST runBrief en vuelo (F1)
  claudeGateBlocked: boolean; // runtime claude_code_cli && !claudeReady
}

/** F1: habilitación del botón "Generar épica". */
export function canGenerateEpic(i: CanGenerateEpicInput): boolean {
  return i.step === "brief" && !i.briefEmpty && !i.isLaunching && !i.claudeGateBlocked;
}

export type ConfirmState = "idle" | "armed";
export type ConfirmEvent = "click" | "timeout" | "disable";

/** F3: máquina de estados del ConfirmButton (two-step).
 *  fire=true SOLO en armed+click (el segundo click). */
export function nextConfirmState(
  state: ConfirmState,
  event: ConfirmEvent,
): { state: ConfirmState; fire: boolean } {
  if (event === "timeout" || event === "disable") return { state: "idle", fire: false };
  if (state === "idle") return { state: "armed", fire: false };
  return { state: "idle", fire: true };
}

/** Estados de ejecución considerados vivos. CONTRATO CRUZADO (plan 134 F0):
 *  son exactamente los 3 estados que consulta fetchActiveRuns en
 *  services/activeRuns.ts (running/preparing/queued). Si el 134 cambia su set,
 *  este debe cambiar igual — sentinela: caso 25 de uiGuards.test.ts. */
export const ACTIVE_RUN_STATUSES = ["running", "preparing", "queued"] as const;

/** F6: decisión de restauración de la consola tras un reload.
 *  "keep" solo si la API confirmó que el run sigue vivo; ante error o estado
 *  desconocido, "clear" (limpiar en silencio). */
export function restoreConsoleDecision(
  status: string | undefined,
  isError: boolean,
): "keep" | "clear" {
  if (isError || !status) return "clear";
  return (ACTIVE_RUN_STATUSES as readonly string[]).includes(status) ? "keep" : "clear";
}

/** F7: toggle de navegación Ctrl+/ (espejo puro del comportamiento). */
export function toggleNavTab(current: string): "team" | "tickets" {
  return current === "team" ? "tickets" : "team";
}
