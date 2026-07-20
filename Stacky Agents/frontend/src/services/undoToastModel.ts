/**
 * undoToastModel.ts — Plan 185 F2. Lógica PURA del host de toasts de undo.
 * Sin React ni DOM: testeable con vitest de módulo puro (no hay RTL/jsdom).
 */
import type { PendingUndoable } from "./undoManager";

/** Visibles: newest-first por createdAt DESC, cap `max` (C4). */
export function visibleToasts(
  pending: PendingUndoable[],
  max = 4,
): PendingUndoable[] {
  return [...pending].sort((a, b) => b.createdAt - a.createdAt).slice(0, max);
}

/** Fracción de gracia restante 0..1 (clamp). 1 = recién creado, 0 = vencido. */
export function remainingRatio(p: PendingUndoable, now: number): number {
  const total = p.expiresAt - p.createdAt;
  if (total <= 0) return 0;
  const remaining = (p.expiresAt - now) / total;
  if (remaining < 0) return 0;
  if (remaining > 1) return 1;
  return remaining;
}

/**
 * true ⇔ (ctrlKey || metaKey) && !altKey && !shiftKey && key==="z"
 *        && el foco NO está en INPUT/TEXTAREA/SELECT ni en un contentEditable.
 * Guard de Ctrl+Z global (no roba el atajo dentro de campos de texto ni el redo).
 */
export function shouldHandleUndoKey(
  ev: {
    key: string;
    ctrlKey: boolean;
    metaKey: boolean;
    altKey: boolean;
    shiftKey: boolean;
  },
  active: { tagName: string; isContentEditable: boolean } | null,
): boolean {
  if (!(ev.ctrlKey || ev.metaKey)) return false;
  if (ev.altKey || ev.shiftKey) return false;
  if (ev.key.toLowerCase() !== "z") return false;
  if (active) {
    if (active.isContentEditable) return false;
    const tag = active.tagName.toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return false;
  }
  return true;
}
