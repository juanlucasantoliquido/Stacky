/**
 * Plan 164 F1 — Reducer PURO de la cola de peticiones del DialogHost + helpers.
 * Sin DOM ni React: modela la cola FIFO de confirmaciones/avisos/entradas y las
 * reglas de settle (C1). DialogHost.tsx envuelve este reducer con estado React.
 */

export type DialogKind = "confirm" | "alert" | "prompt";

/** El valor con el que se resuelve una petición al cerrarse SIN decisión
 *  explícita (Escape/backdrop/✕/Cancelar): valor neutro por kind (C1). */
export function dismissValueFor(kind: DialogKind): boolean | undefined | null {
  switch (kind) {
    case "confirm":
      return false;
    case "alert":
      return undefined;
    case "prompt":
      return null;
  }
}

/** Type-to-confirm, modo A2: habilita confirmar sólo si no hay requiredText o si
 *  el texto coincide EXACTO. */
export function textPromptCanConfirm(value: string, requiredText?: string): boolean {
  if (requiredText == null) return true;
  return value === requiredText;
}

/** Una petición encolada. `resolve` la agrega DialogHost al crear la promesa;
 *  el reducer sólo necesita `id`/`kind`/`opts` para las transiciones puras. */
export interface DialogRequest {
  id: string;
  kind: DialogKind;
  // Opciones libres (título/mensaje/labels/tone/requiredText…); el reducer no
  // las inspecciona, sólo las transporta hacia el componente de marca.
  opts: Record<string, unknown>;
  resolve?: (value: unknown) => void;
}

export interface DialogHostState {
  queue: DialogRequest[];
  current: DialogRequest | null;
}

export type DialogHostAction =
  | { type: "enqueue"; request: DialogRequest }
  | { type: "resolveCurrent"; id: string };

/** Reducer PURO. `enqueue` abre si no hay actual, si no encola; `resolveCurrent`
 *  avanza al siguiente SÓLO si el id coincide con el actual (settle idempotente,
 *  C1: resolver dos veces o con un id stale es no-op → mismo objeto de estado). */
export function dialogHostReducer(
  state: DialogHostState,
  action: DialogHostAction,
): DialogHostState {
  switch (action.type) {
    case "enqueue": {
      if (state.current == null) {
        return { queue: state.queue, current: action.request };
      }
      return { queue: [...state.queue, action.request], current: state.current };
    }
    case "resolveCurrent": {
      // No-op si no hay actual o si el id ya no es el actual (idempotencia).
      if (state.current == null || state.current.id !== action.id) {
        return state;
      }
      const [next, ...rest] = state.queue;
      return { queue: rest, current: next ?? null };
    }
    default:
      return state;
  }
}
