// Plan 157 F5 — lógica pura de ubicación de la gestión de ambientes (testeable con
// vitest). Sin React.
import type { DbEnvironment } from "./dbcompareTypes";

/** Mostrar el CTA prominente de estado vacío: la flag ON y sin ambientes. */
export function shouldShowEmptyCta(envs: DbEnvironment[], flagOn: boolean): boolean {
  return flagOn && envs.length === 0;
}

/** Empujar a agregar otro ambiente: hay al menos 1 pero menos de 2 (no alcanza
 * para comparar). */
export function shouldNudgeAddMore(envs: DbEnvironment[]): boolean {
  return envs.length >= 1 && envs.length < 2;
}
