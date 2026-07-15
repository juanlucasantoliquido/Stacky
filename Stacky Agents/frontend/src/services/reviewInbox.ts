/**
 * Query compartida página↔badge del inbox de revisión (plan 134 F5).
 * MISMA queryKey ⇒ react-query mantiene UNA sola cache y una sola request
 * (con la página abierta manda su intervalo de 30 s; cerrada, el del badge de 60 s).
 */
import { Executions } from "../api/endpoints";
import type { AgentExecution } from "../types";

export const reviewInboxQueryKey = (project: string | null) =>
  ["review-inbox", project] as const;

export function fetchReviewInbox(project: string | null): Promise<AgentExecution[]> {
  return Executions.list({
    project,
    status: ["needs_review", "error"],
    limit: 200,
    days: 30,
  });
}

/** Texto del badge: null = no renderizar badge. */
export function reviewBadgeLabel(count: number): string | null {
  if (count <= 0) return null;
  return count > 99 ? "99+" : String(count);
}
