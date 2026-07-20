/**
 * connectionFlags.ts — Plan 192 F2 (serie UX).
 *
 * Lector de la flag STACKY_CONNECTION_RESILIENCE_ENABLED. WRAPPER sobre el módulo
 * común services/flagGate.ts (fuente única de lectura de flags de UI — 197 §6.1/§8.9):
 * NO duplica el lookup ni el cache. Conserva los nombres que el resto del plan 192
 * consume (readCachedConnectionFlag / isConnectionResilienceEnabled). La semántica
 * fail-open (backend caído => la feature debe VIVIR) la provee flagGate.
 *
 * Nota: la prohibición del D9 v1 ("PROHIBIDO importar de 185/187") quedó OBSOLETA
 * (197 §8.9): flagGate es un módulo común de la serie, no código de 185/187.
 */
import { getBoolFlag, readCachedBoolFlag, resetFlagGateCache } from "./flagGate";

const KEY = "STACKY_CONNECTION_RESILIENCE_ENABLED";

/** Lectura SINCRÓNICA anti-flash. Fail-open: sin cache => true (delega en flagGate). */
export function readCachedConnectionFlag(): boolean {
  return readCachedBoolFlag(KEY);
}

/** 1 request por sesión (promesa cacheada en flagGate); fail-open a true ante error. */
export function isConnectionResilienceEnabled(): Promise<boolean> {
  return getBoolFlag(KEY);
}

/** Test-only: limpia el cache del módulo común. */
export function _resetForTests(): void {
  resetFlagGateCache();
}
