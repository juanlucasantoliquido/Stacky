/**
 * preflightModel.ts — Plan 93 F4. Tipos + funciones PURAS del semáforo de
 * preflight (sin React, sin fetch). Espejo del contrato backend
 * (services/pipeline_preflight.py — normalize_check).
 */

export type PreflightStatus = "ok" | "warn" | "fail" | "unavailable";

export interface PreflightCheck {
  id: string;
  status: PreflightStatus;
  title: string;
  detail: string;
  fix_hint: string;
}

export interface PreflightResult {
  checks: PreflightCheck[];
  summary: Record<string, number>;
}

// Orden de severidad: fail > warn > unavailable > ok
const SEVERITY_ORDER: Record<PreflightStatus, number> = {
  fail: 0,
  warn: 1,
  unavailable: 2,
  ok: 3,
};

/** Peor status del conjunto (fail > warn > unavailable > ok). Inmutable. */
export function overallStatus(checks: PreflightCheck[]): PreflightStatus {
  if (checks.length === 0) return "ok";
  let worst: PreflightStatus = "ok";
  for (const c of checks) {
    if (SEVERITY_ORDER[c.status] < SEVERITY_ORDER[worst]) {
      worst = c.status;
    }
  }
  return worst;
}

/** Ordena por severidad (fail primero, ok último). Estable, no muta el input. */
export function sortBySeverity(checks: PreflightCheck[]): PreflightCheck[] {
  return [...checks].sort((a, b) => SEVERITY_ORDER[a.status] - SEVERITY_ORDER[b.status]);
}

/**
 * [ADICIÓN ARQUITECTO] Una línea en llano para el operador:
 * "N problema(s), M aviso(s), K sin verificar" con los títulos de fail/warn
 * concatenados; todos ok -> "Todo verde: el pipeline debería funcionar".
 */
export function summaryLine(checks: PreflightCheck[]): string {
  const fails = checks.filter((c) => c.status === "fail");
  const warns = checks.filter((c) => c.status === "warn");
  const unavailables = checks.filter((c) => c.status === "unavailable");

  if (fails.length === 0 && warns.length === 0 && unavailables.length === 0) {
    return "Todo verde: el pipeline debería funcionar";
  }

  const parts: string[] = [];
  if (fails.length > 0) {
    const word = fails.length === 1 ? "problema" : "problemas";
    parts.push(`${fails.length} ${word}`);
  }
  if (warns.length > 0) {
    const word = warns.length === 1 ? "aviso" : "avisos";
    parts.push(`${warns.length} ${word}`);
  }
  if (unavailables.length > 0) {
    const word = unavailables.length === 1 ? "check sin verificar" : "checks sin verificar";
    parts.push(`${unavailables.length} ${word}`);
  }

  const titles = [...fails, ...warns].map((c) => c.title).join("; ");
  const summary = parts.join(", ");
  return titles ? `${summary}: ${titles}` : summary;
}
