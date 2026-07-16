import type { IntegrationHealthItem, IntegrationsStatusResponse } from "../api/endpoints";

/**
 * integrationHealth.logic.ts — Plan 148 F6.
 *
 * Lógica PURA de IntegrationHealthBanner.tsx, separada para poder testearla con
 * vitest sin necesitar @testing-library/react + jsdom (gap estructural del
 * frontend: ninguno de los dos está en package.json). El componente importa
 * estas funciones en vez de reimplementar la decisión inline.
 */

/** Con la flag master OFF, /status responde `enabled:false` -> no mostrar nada. */
export function resolveVisibleIntegrations(
  data: IntegrationsStatusResponse | null | undefined,
): IntegrationHealthItem[] {
  if (!data || !data.enabled) return [];
  return data.integrations;
}

/** El banner completo (todas las filas) no debe renderizar nada si no hay caídas. */
export function shouldRenderBanner(items: IntegrationHealthItem[]): boolean {
  return items.length > 0;
}
