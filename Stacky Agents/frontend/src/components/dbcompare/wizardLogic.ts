// Plan 124 — Comparador de BD: lógica pura del wizard de comparación (doc §F2).
import type { DbEnvironment } from "./dbcompareTypes";

export interface SelectableTarget {
  alias: string;
  enabled: boolean;
  reason: string;
}

/**
 * Determina, para cada ambiente candidato, si puede seleccionarse como DESTINO dado el
 * ORIGEN ya elegido. Reglas (doc §F2):
 *  (a) el destino solo habilita ambientes del MISMO engine que el origen;
 *  (b) el mismo alias no puede ser origen y destino;
 *  (c) sin password -> deshabilitado.
 */
export function selectableTargets(
  envs: DbEnvironment[],
  source: DbEnvironment | null
): SelectableTarget[] {
  if (!source) {
    return envs.map((e) => ({
      alias: e.alias,
      enabled: false,
      reason: "Elegí primero un ambiente de origen.",
    }));
  }
  return envs.map((e) => {
    if (e.alias === source.alias) {
      return { alias: e.alias, enabled: false, reason: "El mismo ambiente no puede ser origen y destino." };
    }
    if (e.engine !== source.engine) {
      return {
        alias: e.alias,
        enabled: false,
        reason: `Motor distinto (el origen es ${source.engine}).`,
      };
    }
    if (!e.has_password) {
      return { alias: e.alias, enabled: false, reason: "Este ambiente no tiene contraseña configurada." };
    }
    return { alias: e.alias, enabled: true, reason: "" };
  });
}

export interface LaunchCheck {
  ok: boolean;
  reason: string;
}

/** Valida si el par (origen, destino) elegido habilita el botón "Comparar ambientes". */
export function canLaunch(source: DbEnvironment | null, target: DbEnvironment | null): LaunchCheck {
  if (!source) return { ok: false, reason: "Elegí un ambiente de origen." };
  if (!target) return { ok: false, reason: "Elegí un ambiente de destino." };
  if (source.alias === target.alias) {
    return { ok: false, reason: "Origen y destino no pueden ser el mismo ambiente." };
  }
  if (source.engine !== target.engine) {
    return { ok: false, reason: "Origen y destino deben ser del mismo motor." };
  }
  if (!source.has_password) {
    return { ok: false, reason: "El ambiente de origen no tiene contraseña configurada." };
  }
  if (!target.has_password) {
    return { ok: false, reason: "El ambiente de destino no tiene contraseña configurada." };
  }
  return { ok: true, reason: "" };
}
