/**
 * Plan 265 F1 — Presentación de la consola de corridas: "dock" | "full" | "minimized".
 * Lógica pura, sin React (el repo no tiene RTL ni jsdom).
 */

export type ConsolePresentation = "dock" | "full" | "minimized";

export const DEFAULT_PRESENTATION: ConsolePresentation = "dock";

const VALID_PRESENTATIONS: ConsolePresentation[] = ["dock", "full", "minimized"];

/** Normaliza cualquier valor rehidratado (o de un deploy viejo) a una presentación válida. */
export function normalizePresentation(raw: unknown): ConsolePresentation {
  if (typeof raw === "string" && VALID_PRESENTATIONS.includes(raw as ConsolePresentation)) {
    return raw as ConsolePresentation;
  }
  return DEFAULT_PRESENTATION;
}

/** Migración del booleano viejo. `codexConsoleMinimized === true` -> "minimized", si no "dock". */
export function presentationFromLegacy(minimized: boolean | undefined): ConsolePresentation {
  return minimized === true ? "minimized" : "dock";
}

/** El booleano que hay que seguir escribiendo para no romper deploys viejos. */
export function legacyMinimizedFrom(p: ConsolePresentation): boolean {
  return p === "minimized";
}

/** Alterna dock <-> full. Desde "minimized" va a "dock" (un paso a la vez, sin saltos). */
export function togglePresentation(current: ConsolePresentation): ConsolePresentation {
  if (current === "dock") return "full";
  if (current === "full") return "dock";
  return "dock"; // "minimized" -> "dock": un paso a la vez, nunca directo a "full"
}

/** ¿Se oculta el chrome de la app (nav, topbar) con esta presentación? */
export function hidesAppChrome(p: ConsolePresentation): boolean {
  return p === "full";
}
