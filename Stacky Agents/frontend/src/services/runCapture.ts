/**
 * Plan 152 F2 — Helpers PUROS de la captura de runs y de la transición de costo.
 *
 * Sin DOM, sin red, sin timers: solo comparaciones deterministas. El wiring con
 * react-query vive en hooks/useRunActivityCapture.ts (que no agrega requests: se
 * cuelga de la query compartida ya existente).
 */

/**
 * Ids que estaban en `prev` y ya NO están en `current` (finalizaron o
 * desaparecieron del set activo). Con `prev === null` (primer snapshot) devuelve
 * [] para no emitir falsos positivos de arranque.
 */
export function diffFinishedIds(prev: Set<number> | null, current: Set<number>): number[] {
  if (prev == null) return [];
  const out: number[] = [];
  for (const id of prev) {
    if (!current.has(id)) out.push(id);
  }
  return out;
}

const ALERTING = new Set(["alert", "over", "blocked"]);

/**
 * true SOLO si `next` es un estado de alerta ({alert,over,blocked}) y difiere de
 * `prev`. Repetir el mismo estado (poll de 60 s del indicador de costo) NO
 * dispara evento; una transición nueva (alert→over) sí. Anti-ruido de F6b.
 */
export function shouldPublishCostTransition(prev: string | null, next: string): boolean {
  return ALERTING.has(next) && next !== prev;
}
