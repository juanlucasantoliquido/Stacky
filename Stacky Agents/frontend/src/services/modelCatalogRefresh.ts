/** Plan 288 F9.1 — ¿corresponde volver a pedir el catálogo? FUNCIÓN PURA.
 *
 * Existe separada del hook porque la lógica tiene que poder probarse sin DOM.
 * La regla es deliberadamente conservadora: esto NO es un sondeo. Solo dice que
 * sí cuando la pestaña está a la vista Y ya venció el tiempo de vida.
 */
export function debeRefrescarCatalogo(
  visible: boolean,
  pedidoEnMs: number,
  ahoraMs: number,
  ttlMs: number,
): boolean {
  // Con la pestaña oculta NUNCA se pide: es lo que impide el sondeo de fondo.
  if (!visible) return false;
  // Nunca se pidió todavía.
  if (!pedidoEnMs) return true;
  // Reloj hacia atrás (cambio de hora, suspensión): se trata como vencido, que
  // es el lado seguro — a lo sumo una petición de más, nunca una lista podrida.
  if (ahoraMs < pedidoEnMs) return true;
  return ahoraMs - pedidoEnMs >= ttlMs;
}
