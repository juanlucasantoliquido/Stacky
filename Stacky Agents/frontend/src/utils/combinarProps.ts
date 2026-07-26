/**
 * Plan 174 F3 — Une dos juegos de props sin que uno pise al otro.
 *
 * Roving (plan 172) y prefetch (174) declaran los dos un `onFocus`. Con un
 * spread crudo el segundo gana y el primero desaparece EN SILENCIO: el foco
 * dejaría de sincronizar el índice y nadie se enteraría hasta usar j/k y ver
 * que salta a la fila equivocada.
 */
export function combinarProps(
  a: Record<string, unknown>,
  b: Record<string, unknown>,
): Record<string, unknown> {
  const salida: Record<string, unknown> = { ...a };
  for (const [k, v] of Object.entries(b)) {
    const previo = salida[k];
    salida[k] =
      typeof previo === "function" && typeof v === "function"
        ? (...args: unknown[]) => {
            (previo as (...a: unknown[]) => void)(...args);
            (v as (...a: unknown[]) => void)(...args);
          }
        : v;
  }
  return salida;
}
