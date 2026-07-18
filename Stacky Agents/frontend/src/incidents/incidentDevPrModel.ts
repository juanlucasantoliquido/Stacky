/**
 * Plan 177 F5 — Modelo PURO del checkbox "Abrir PR" del board. Sin DOM
 * (testeable con vitest solo, respeta el gap RTL/jsdom). El checkbox viene
 * PREMARCADO por directiva del operador (2026-07-18): resolver una incidencia
 * abre un PR salvo que se desmarque.
 */

export const DEFAULT_OPEN_PR = true; // premarcado

export function shouldShowOpenPrCheckbox(args: {
  canResolve: boolean;
  devPrEnabled: boolean;
}): boolean {
  return args.canResolve && args.devPrEnabled;
}
