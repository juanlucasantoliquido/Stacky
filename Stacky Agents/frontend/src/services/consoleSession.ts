/**
 * Plan 265 F1.5 — La identidad de sesión de la consola como invariante EJECUTABLE.
 * Lógica pura, sin React. Ningún cambio de presentación puede tocar la sesión.
 */
import type { ConsolePresentation } from "./consolePresentation";
import { normalizePresentation, legacyMinimizedFrom } from "./consolePresentation";

/** El subconjunto del estado del workbench del que depende la IDENTIDAD de la sesión.
 *  Todo lo demás es presentación. */
export interface SessionBearingState {
  codexConsoleExecutionId: number | null;
  codexConsolePresentation: ConsolePresentation;
  codexConsoleMinimized: boolean;
}

/** Token de identidad de sesión. Dos estados con el MISMO token miran la misma
 *  conversación; el stream no se re-suscribe y el ring-buffer no se vacía.
 *  Deliberadamente NO incluye la presentación: cambiar de presentación no puede
 *  cambiar de sesión. Nunca lanza ante entrada degenerada. */
export function sessionIdentity(s: SessionBearingState): string {
  const id = s?.codexConsoleExecutionId ?? null;
  return `console-session:${id === null ? "none" : id}`;
}

/** Aplica una transición de presentación sobre el estado. Es el ÚNICO lugar donde
 *  se calcula el próximo estado de consola: el setter del store lo llama y no
 *  hace aritmética propia. Nunca lanza. NUNCA toca codexConsoleExecutionId. */
export function applyPresentation(
  s: SessionBearingState,
  next: ConsolePresentation,
): SessionBearingState {
  const p = normalizePresentation(next);
  const executionId = s?.codexConsoleExecutionId ?? null;
  return {
    codexConsoleExecutionId: executionId,
    codexConsolePresentation: p,
    codexConsoleMinimized: legacyMinimizedFrom(p),
  };
}

/** ¿Abrir la pantalla completa sobre este estado crea una sesión nueva?
 *  SIEMPRE false mientras haya `codexConsoleExecutionId`. Si es `null` no hay
 *  sesión que preservar y la consola full arranca vacía, que es lo correcto. */
export function opensNewSession(s: SessionBearingState, _next: ConsolePresentation): boolean {
  const executionId = s?.codexConsoleExecutionId ?? null;
  return executionId === null;
}
