/** Plan 295 F10 — de qué valor sale el intervalo de auto-sync.
 *
 *  Vive en un módulo propio y PURO para poder probarlo con vitest sin renderizar:
 *  RTL y jsdom NO están instalados en este repo, y un .test.tsx con RTL reporta
 *  "no tests" y sale con exit 0 -- un falso verde. Vitest sí corre .ts puro.
 *
 *  El fallback NO es decorativo: `Tickets.frontendConfig()` pasa por el wrapper
 *  `api.get`, que LANZA en non-2xx. Si el endpoint de config estuviera caído, el
 *  valor llegaría `undefined` y sin este `?? fallback` el tablero se quedaría sin
 *  auto-sync. Un intervalo 0 o negativo sería un bucle de red.
 */
export function intervaloDeSync(
  delBackend: number | null | undefined,
  fallback: number,
): number {
  if (typeof delBackend !== "number" || !Number.isFinite(delBackend)) return fallback;
  if (delBackend <= 0) return fallback;
  return delBackend;
}
