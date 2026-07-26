// Plan 174 F3 — Cuándo vale la pena precargar algo que el operador todavía no pidió.
//
// El presupuesto es duro a propósito: precargar de más convierte una mejora de
// percepción en una tormenta de requests. Techo = 1 en vuelo, y el debounce
// descarta el hover de paso (el mouse cruzando la tabla hacia otro lado).
//
// Lo que YA salió a la red no se aborta: abortar un GET barato ya emitido cuesta
// más que dejarlo poblar la cache.

export const PREFETCH_HOVER_DELAY_MS = 150;
export const PREFETCH_MAX_CONCURRENT = 1;
export const PREFETCH_DETAIL_STALE_TIME_MS = 30_000;

export interface PrefetchTimer {
  set: (fn: () => void, ms: number) => number;
  clear: (id: number) => void;
}

export interface PrefetchScheduler {
  enter: (key: string) => void;
  leave: (key: string) => void;
  inFlightCount: () => number;
  dispose: () => void;
}

const TIMER_REAL: PrefetchTimer = {
  set: (fn, ms) => setTimeout(fn, ms) as unknown as number,
  clear: (id) => clearTimeout(id),
};

export function createPrefetchScheduler(
  run: (key: string) => Promise<unknown>,
  timer: PrefetchTimer = TIMER_REAL,
): PrefetchScheduler {
  const pendientes = new Map<string, number>();
  const enVuelo = new Set<string>();

  function enter(key: string): void {
    // Re-entrar con un timer ya armado no acumula timers: si no, pasar el mouse
    // en zigzag sobre una fila dispararía N prefetches de la misma cosa.
    if (pendientes.has(key) || enVuelo.has(key)) return;

    const id = timer.set(() => {
      pendientes.delete(key);
      // Techo duro. El que no entra se DESCARTA, no se encola: una cola
      // convertiría un paseo del mouse por la tabla en 30 requests diferidos.
      if (enVuelo.size >= PREFETCH_MAX_CONCURRENT) return;
      if (enVuelo.has(key)) return;
      enVuelo.add(key);
      Promise.resolve(run(key))
        .catch(() => undefined)
        .finally(() => enVuelo.delete(key));
    }, PREFETCH_HOVER_DELAY_MS);
    pendientes.set(key, id);
  }

  function leave(key: string): void {
    const id = pendientes.get(key);
    if (id === undefined) return;
    timer.clear(id);
    pendientes.delete(key);
  }

  function dispose(): void {
    for (const id of pendientes.values()) timer.clear(id);
    pendientes.clear();
  }

  return { enter, leave, inFlightCount: () => enVuelo.size, dispose };
}
