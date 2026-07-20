// Plan 180 — Puente diff->repo: logica pura del panel de cobertura.
// Sin React, sin fetch: funciones deterministas testeables por vitest (sin RTL/jsdom).

import type { RepoCoverage, RepoCoverageItem } from "./repoCoverageTypes";

export interface CoverageSummary {
  covered: number;
  total: number;
  pct: number;
}

/**
 * Resumen "N de M". Devuelve null si no hay cobertura o el diff no tiene items
 * (total_count === 0) — en ese caso el panel NO se renderiza. pct con Math.round.
 */
export function coverageSummary(coverage: RepoCoverage | null): CoverageSummary | null {
  if (coverage === null) return null;
  const total = coverage.total_count;
  if (total === 0) return null;
  const covered = coverage.covered_count;
  return { covered, total, pct: Math.round((covered / total) * 100) };
}

export interface TicketGroup {
  ticket: string | null;
  paths: string[];
}

/**
 * Agrupa TODOS los candidatos de todos los items por ticket. Orden: tickets
 * numericos ascendente, null al final. paths dedup (orden de primera aparicion).
 */
export function groupCandidatesByTicket(items: RepoCoverageItem[]): TicketGroup[] {
  const byTicket = new Map<string | null, string[]>();
  for (const item of items) {
    for (const cand of item.candidates) {
      const ticket = cand.ticket ?? null;
      const paths = byTicket.get(ticket) ?? [];
      if (!paths.includes(cand.path)) paths.push(cand.path);
      byTicket.set(ticket, paths);
    }
  }
  const groups: TicketGroup[] = [];
  for (const [ticket, paths] of byTicket.entries()) {
    groups.push({ ticket, paths });
  }
  groups.sort((a, b) => {
    if (a.ticket === null && b.ticket === null) return 0;
    if (a.ticket === null) return 1; // null al final
    if (b.ticket === null) return -1;
    return Number(a.ticket) - Number(b.ticket); // numerico ascendente
  });
  return groups;
}

const _SEVERITY_RANK: Record<string, number> = { danger: 0, warn: 1, info: 2 };

function _severityRank(severity: string | null): number {
  if (severity === null) return 3;
  const rank = _SEVERITY_RANK[severity];
  return rank === undefined ? 3 : rank;
}

/**
 * Ordena los items por severidad (danger < warn < info < otro); empate por
 * "schema.name" ascendente. No muta el array de entrada.
 */
export function severityOrder(items: RepoCoverageItem[]): RepoCoverageItem[] {
  return [...items].sort((a, b) => {
    const bySev = _severityRank(a.severity) - _severityRank(b.severity);
    if (bySev !== 0) return bySev;
    const keyA = `${a.schema ?? ""}.${a.name ?? ""}`;
    const keyB = `${b.schema ?? ""}.${b.name ?? ""}`;
    return keyA < keyB ? -1 : keyA > keyB ? 1 : 0;
  });
}
