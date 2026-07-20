// frontend/src/services/settingsSubTabs.ts — Plan 165 F3
// Sub-tabs de Settings extraídos a un módulo PURO (sin JSX) para que el contrato
// de rutas y sus tests los consuman sin arrastrar SettingsPage.tsx (que importa
// componentes que tocan window/Notification al cargar; el vitest de este repo no
// tiene jsdom). Fuente única de la lista de sub-tabs direccionables por path.

export type SubTab =
  | "flow" | "sections" | "client-profile" | "transfer" | "webhooks"
  | "notifications" | "harness" | "playground" | "appearance";

export const SETTINGS_SUB_TABS: readonly SubTab[] = [
  "flow", "sections", "client-profile", "transfer", "webhooks",
  "notifications", "harness", "playground", "appearance",
];

/** true si x es una de las 9 claves de SubTab (pura, testeable sin jsdom). */
export function isValidSubTab(x: unknown): x is SubTab {
  return typeof x === "string" && (SETTINGS_SUB_TABS as readonly string[]).includes(x);
}
