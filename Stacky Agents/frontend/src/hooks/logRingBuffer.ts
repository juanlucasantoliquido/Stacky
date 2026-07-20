/**
 * Plan 156 F3 — Ring-buffer puro del stream de logs.
 *
 * Acota `lines` a un máximo (LOG_RING_CAP) y mantiene el Set `seen` de dedup
 * ATADO a la misma ventana (dedup window == ring window): cuando una línea sale
 * del ring, su clave sale de `seen`. Todo es puro y testeable sin DOM.
 */
import type { LogLine } from "../types";

export const LOG_RING_CAP = 5000;

/** Clave de dedup (movida desde useExecutionStream para poder evictarla). */
export function dedupKey(l: LogLine): string {
  return `${l.timestamp ?? ""}|${l.level ?? ""}|${l.message ?? ""}`;
}

export interface RingState {
  lines: LogLine[];
  seen: Set<string>;
  dropped: number;
}

export function emptyRing(): RingState {
  return { lines: [], seen: new Set(), dropped: 0 };
}

/** Append acotado + dedup dentro de ventana + evict simétrico del Set.
 *  Devuelve el MISMO objeto si la línea era duplicado en ventana (no-op). */
export function appendBounded(
  state: RingState,
  line: LogLine,
  cap: number = LOG_RING_CAP,
): RingState {
  const key = dedupKey(line);
  if (state.seen.has(key)) return state; // duplicado dentro de la ventana actual

  const seen = new Set(state.seen);
  seen.add(key);
  let lines = [...state.lines, line];
  let dropped = state.dropped;

  if (lines.length > cap) {
    const removeCount = lines.length - cap;
    for (let i = 0; i < removeCount; i++) {
      // evict simétrico: la clave de la línea que sale del ring sale del Set.
      // Consecuencia ACEPTADA: un duplicado tardío de esa línea puede re-entrar
      // (su original ya no está en ventana). dedup window == ring window.
      seen.delete(dedupKey(lines[i]));
    }
    lines = lines.slice(removeCount);
    dropped += removeCount;
  }
  return { lines, seen, dropped };
}
