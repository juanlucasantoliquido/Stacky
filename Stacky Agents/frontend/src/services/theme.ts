/* Plan 141 F0 — núcleo puro de resolución de tema (sin DOM, sin efectos). */

export type ThemeChoice = "dark" | "light" | "system";
export type EffectiveTheme = "dark" | "light";

/** Clave localStorage CONGELADA por el arquitecto (plan 141). NO renombrar. */
export const THEME_STORAGE_KEY = "stacky.ui.theme";

/** Normaliza un valor crudo a un ThemeChoice. Default byte-idéntico: "dark". */
export function normalizeChoice(raw: string | null | undefined): ThemeChoice {
  return raw === "light" || raw === "system" ? raw : "dark";
}

/** Resuelve el tema EFECTIVO. Pura. `prefersDark` = matchMedia del SO. */
export function resolveTheme(
  stored: string | null | undefined,
  prefersDark: boolean,
): EffectiveTheme {
  const choice = normalizeChoice(stored);
  if (choice === "system") return prefersDark ? "dark" : "light";
  return choice; // "dark" | "light"
}
