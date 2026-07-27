/**
 * Plan 166 F5 — Modelo PURO de disponibilidad del botón "Resolver con
 * agente" en las Issues del board. Sin dependencias de DOM: testeable con
 * vitest solo (respeta el gap RTL/jsdom, ver gotcha-rtl-jsdom-structural-gap).
 * El wiring del botón se valida en el smoke manual (F6).
 */

import { isIncidentWorkItemType } from "../utils/workItemTypeColor";

export function canResolveWithAgent(args: {
  workItemType?: string | null;
  adoState?: string | null;
  isRunning: boolean;
  enabled: boolean;
  closedStates: string[];
}): boolean {
  const isIssue = isIncidentWorkItemType(args.workItemType);
  const isClosed = args.closedStates.includes(args.adoState ?? "");
  return isIssue && args.enabled && !args.isRunning && !isClosed;
}
