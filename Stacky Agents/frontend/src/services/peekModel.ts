// Plan 175 F2 — Vista previa al hover sostenido. Reducer y builders PUROS.
//
// Los dos tiempos importan: 400 ms para abrir (para que pasar el mouse por
// encima camino a otro lado NO dispare tarjetas), y 150 ms de tolerancia al
// cerrar (para poder mover el mouse HACIA la tarjeta sin que se escape).

import type { ExecutionHistoryItem } from "../api/endpoints";
import type { Ticket } from "../types";
import { formatRelativeTime } from "../utils/formatRelativeTime";
import type { EntityKind } from "./entityActions";
import {
  formatCostUsd,
  formatDateTime,
  formatDuration,
  formatInt,
  formatTokens,
} from "./format";

export const PEEK_OPEN_DELAY_MS = 400;
export const PEEK_CLOSE_DELAY_MS = 150;

export type PeekTarget = { kind: EntityKind; id: number };
export type PeekPhase = "idle" | "arming" | "open" | "closing";

export interface PeekState {
  phase: PeekPhase;
  target: PeekTarget | null;
}

export type PeekEvent =
  | { type: "hover-start"; target: PeekTarget }
  | { type: "open-timer" }
  | { type: "hover-end" }
  | { type: "card-hover" }
  | { type: "close-timer" }
  | { type: "escape" }
  | { type: "force-close" };

export const PEEK_IDLE: PeekState = { phase: "idle", target: null };

export function peekReducer(s: PeekState, e: PeekEvent): PeekState {
  switch (e.type) {
    case "hover-start":
      return { phase: "arming", target: e.target };
    case "open-timer":
      // Solo abre si SIGUE armado: si el mouse ya se fue, el timer que llega
      // tarde no puede abrir una tarjeta sobre una fila que nadie está mirando.
      return s.phase === "arming" ? { ...s, phase: "open" } : s;
    case "hover-end":
      if (s.phase === "arming") return PEEK_IDLE;
      if (s.phase === "open") return { ...s, phase: "closing" };
      return s;
    case "card-hover":
      // Entrar a la tarjeta cancela el cierre: si no, no se podría leerla ni
      // copiar nada de adentro.
      return s.phase === "closing" ? { ...s, phase: "open" } : s;
    case "close-timer":
      return s.phase === "closing" ? PEEK_IDLE : s;
    case "escape":
    case "force-close":
      return PEEK_IDLE;
  }
}

export interface PeekField {
  label: string;
  value: string;
  mono?: boolean;
}

export interface PeekContent {
  title: string;
  fields: PeekField[];
}

/** Un mensaje de error de 4 KB reventaría la tarjeta: se corta y se avisa. */
function truncar(texto: string, max: number): string {
  const s = String(texto ?? "");
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

export function buildExecutionPeek(it: ExecutionHistoryItem): PeekContent {
  const fields: PeekField[] = [
    { label: "Estado", value: it.status },
    { label: "Inicio", value: formatDateTime(it.started_at) },
    { label: "Duración", value: formatDuration(it.duration_ms) },
    { label: "Costo", value: formatCostUsd(it.cost_usd) },
    { label: "Tokens", value: `${formatTokens(it.tokens_in)} in · ${formatTokens(it.tokens_out)} out` },
    { label: "Runtime", value: it.runtime ?? "—", mono: true },
    { label: "Modelo", value: it.model ?? "—", mono: true },
    { label: "Archivos", value: formatInt(it.produced_files_count) },
    { label: "Ticket", value: it.ticket_title ?? `#${it.ticket_id}` },
  ];
  if (it.error_message) {
    fields.push({ label: "Error", value: truncar(it.error_message, 120) });
  }
  return {
    title: `Ejecución #${it.id} — ${it.agent_name ?? it.agent_type}`,
    fields,
  };
}

export function buildTicketPeek(t: Ticket): PeekContent {
  const fields: PeekField[] = [
    { label: "Tipo", value: t.work_item_type ?? "—" },
    { label: "Estado ADO", value: t.ado_state ?? "—" },
    { label: "Estado Stacky", value: t.stacky_status ?? "—" },
    { label: "Prioridad", value: t.priority != null ? formatInt(t.priority) : "—" },
    { label: "Asignado", value: t.assigned_to_ado ?? "—" },
    { label: "Sync", value: formatRelativeTime(t.last_synced_at) },
  ];
  const p = t.pipeline_summary;
  if (p) {
    // El field solo aparece si hay pipeline: mostrar "0 etapas" en un ticket que
    // no tiene pipeline sugeriría que algo falló.
    fields.push({
      label: "Pipeline",
      value: `${(p.done_stages ?? []).length} etapas · próx: ${p.next_suggested ?? "—"}`,
    });
  }
  return { title: `ADO-${t.ado_id} — ${truncar(t.title ?? "", 80)}`, fields };
}
