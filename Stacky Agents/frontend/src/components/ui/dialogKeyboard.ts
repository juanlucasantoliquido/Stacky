/**
 * Plan 164 F1 — Helpers PUROS de teclado/foco de la primitiva Dialog.
 * Sin DOM ni React: 100% testeable con vitest puro (RTL/jsdom no están en el
 * repo). Dialog.tsx consume estos helpers; acá vive toda la lógica de decisión.
 */
import { shouldCloseOnBackdrop } from "../../services/uiGuards";

export type DialogKeyAction = "close" | "focus-first" | "focus-last" | null;

/** Decide la acción de teclado de un diálogo modal.
 *  atFirst/atLast: si el foco está en el primer/último enfocable. */
export function dialogKeydownAction(
  key: string,
  shiftKey: boolean,
  pos: { atFirst: boolean; atLast: boolean },
): DialogKeyAction {
  if (key === "Escape") return "close";
  if (key === "Tab" && !shiftKey && pos.atLast) return "focus-first"; // wrap hacia adelante
  if (key === "Tab" && shiftKey && pos.atFirst) return "focus-last"; // wrap hacia atrás
  return null;
}

/** Índice del próximo enfocable con wraparound (para el focus-trap). */
export function nextFocusableIndex(
  count: number,
  current: number,
  shiftKey: boolean,
): number {
  if (count <= 0) return -1;
  const delta = shiftKey ? -1 : 1;
  return (current + delta + count) % count;
}

/** ¿El diálogo puede cerrar por Escape/backdrop? Reusa la guarda ya testeada
 *  del plan 136 (shouldCloseOnBackdrop). El cierre por botón explícito
 *  (✕/Cancelar) NO pasa por acá: es intención directa. */
export function canCloseByGuard(guard?: { dirty: boolean; busy: boolean }): boolean {
  if (!guard) return true;
  return shouldCloseOnBackdrop(guard);
}

/** Selector CSS de elementos enfocables dentro del panel (para el focus-trap). */
export const FOCUSABLE_SELECTOR =
  'a[href],button:not([disabled]),input:not([disabled]),' +
  'select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
