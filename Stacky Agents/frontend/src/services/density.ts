/* Plan 150 F1 — lógica pura de densidad (sin DOM). */
export type Density = "comodo" | "compacto";

/** Clave localStorage CONGELADA (espejo dotted de stacky.ui.theme del 141). */
export const DENSITY_STORAGE_KEY = "stacky.ui.density" as const;

/** Normaliza un valor crudo a Density. Default byte-idéntico: "comodo". */
export function normalizeDensity(raw: string | null | undefined): Density {
  return raw === "compacto" ? "compacto" : "comodo";
}
