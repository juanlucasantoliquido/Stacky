/**
 * Plan 166 F5 — Modelo PURO de disponibilidad del botón "Resolver con
 * agente" en las Issues del board. Sin dependencias de DOM: testeable con
 * vitest solo (respeta el gap RTL/jsdom, ver gotcha-rtl-jsdom-structural-gap).
 * El wiring del botón se valida en el smoke manual (F6).
 */

export function canResolveWithAgent(args: {
  workItemType?: string | null;
  adoState?: string | null;
  isRunning: boolean;
  enabled: boolean;
  closedStates: string[];
}): boolean {
  const isIssue = ["issue", "bug"].includes((args.workItemType ?? "").toLowerCase());
  const isClosed = args.closedStates.includes(args.adoState ?? "");
  return isIssue && args.enabled && !args.isRunning && !isClosed;
}
