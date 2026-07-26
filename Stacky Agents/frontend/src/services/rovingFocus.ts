// Plan 172 F4 — Recorrer una lista con el teclado. PURO: cero DOM.
//
// Sin wraparound a propósito: llegar al final y saltar al principio hace perder
// la referencia de dónde se está en una lista larga. Se clampea y punto.

export type RovingAction = "next" | "prev" | "first" | "last" | "open" | "escape" | null;

/**
 * Tecla → acción. Con Ctrl/Meta/Alt SIEMPRE devuelve null: secuestrar Ctrl+End
 * o Alt+flecha rompería atajos del navegador que el operador ya usa.
 */
export function rovingActionForKey(key: string, hasModifier: boolean): RovingAction {
  if (hasModifier) return null;
  switch (key) {
    case "j":
    case "J":
    case "ArrowDown":
      return "next";
    case "k":
    case "K":
    case "ArrowUp":
      return "prev";
    case "Home":
      return "first";
    case "End":
      return "last";
    case "Enter":
      return "open";
    case "Escape":
      return "escape";
    default:
      return null;
  }
}

/** Próximo índice, con clamp. Sin fila activa (-1): next/first van a la primera,
 *  prev/last a la última. */
export function nextRovingIndex(
  action: "next" | "prev" | "first" | "last",
  current: number,
  count: number,
): number {
  if (count <= 0) return -1;
  const ultimo = count - 1;
  if (action === "first") return 0;
  if (action === "last") return ultimo;
  if (current < 0) return action === "next" ? 0 : ultimo;
  const destino = action === "next" ? current + 1 : current - 1;
  return Math.max(0, Math.min(ultimo, destino));
}

/** Reajusta el índice activo cuando la lista cambia de tamaño.
 *  Sin esto, borrar el último elemento deja el foco apuntando a la nada. */
export function clampRovingIndex(current: number, count: number): number {
  if (count <= 0) return -1;
  if (current < 0) return -1;
  return Math.min(current, count - 1);
}
