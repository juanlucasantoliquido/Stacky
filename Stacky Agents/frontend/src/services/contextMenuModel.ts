// Plan 175 F3 — Menú contextual: dónde se dibuja, cómo se recorre con el
// teclado, y cómo se arma una acción con efecto. Todo PURO.

export interface MenuPosition {
  left: number;
  top: number;
}

/** Si el menú no entra hacia abajo/derecha, se voltea. Un menú que se sale del
 *  viewport es un menú del que la mitad de las acciones no se pueden clickear. */
export function clampMenuPosition(
  x: number,
  y: number,
  menuW: number,
  menuH: number,
  vw: number,
  vh: number,
  margin = 8,
): MenuPosition {
  let left = x;
  let top = y;
  if (x + menuW > vw - margin) left = x - menuW;
  if (y + menuH > vh - margin) top = y - menuH;
  // El margen mínimo evita que quede pegado al borde incluso en un viewport
  // más chico que el propio menú.
  return { left: Math.max(margin, left), top: Math.max(margin, top) };
}

export type MenuKeyResult =
  | { kind: "move"; index: number }
  | { kind: "select" }
  | { kind: "close" }
  | { kind: "none" };

export function menuKeydown(key: string, index: number, count: number): MenuKeyResult {
  if (key === "Escape") return { kind: "close" };
  // Con el menú vacío no hay nada que mover ni seleccionar: solo se puede salir.
  if (count <= 0) return { kind: "none" };

  switch (key) {
    // Acá el wrap SÍ va: un menú corto se recorre en círculo sin pensar.
    case "ArrowDown":
      return { kind: "move", index: (index + 1) % count };
    case "ArrowUp":
      return { kind: "move", index: (index - 1 + count) % count };
    case "Home":
      return { kind: "move", index: 0 };
    case "End":
      return { kind: "move", index: count - 1 };
    case "Enter":
    case " ":
      return { kind: "select" };
    default:
      return { kind: "none" };
  }
}

export interface ArmState {
  armedId: string | null;
}

export type ArmEvent =
  | { type: "activate"; id: string; effect: "safe" | "confirm" }
  | { type: "escape" }
  | { type: "close" };

/**
 * Armado en dos pasos para lo que tiene efecto: el primer click arma, el segundo
 * dispara. Es la confirmación humana sin depender de un diálogo — y evita que un
 * click de más borre una ejecución.
 */
export function armTransition(
  s: ArmState,
  e: ArmEvent,
): { state: ArmState; fire: string | null } {
  if (e.type === "escape" || e.type === "close") {
    return { state: { armedId: null }, fire: null };
  }
  if (e.effect === "safe") {
    return { state: { armedId: null }, fire: e.id };
  }
  if (s.armedId === e.id) {
    return { state: { armedId: null }, fire: e.id };
  }
  // Activar OTRO ítem re-arma en vez de disparar: si no, tener uno armado
  // convertiría el siguiente click en una acción no querida.
  return { state: { armedId: e.id }, fire: null };
}
