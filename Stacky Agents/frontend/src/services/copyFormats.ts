/**
 * copyFormats.ts — Plan 194 F2. Formateadores 100% PUROS: entidades y tablas
 * → Markdown / CSV / HTML / Texto, con escapado correcto.
 *
 * Decisiones fijadas: CSV coma + CRLF + sin BOM (§4.1); Markdown pipes escapados
 * + saltos → espacio (§4.2); fechas SIEMPRE ISO crudo (§4.10 — PROHIBIDO
 * formatDate*); duración/costo vía services/format (G9).
 */
import type { Ticket, AgentExecution } from "../types";
import type { IncidentDTO } from "../incidents/incidentModel";
import type { ExecutionHistoryItem } from "../api/endpoints";
import { adoUrl } from "../utils/trackerUrls";
import { formatDuration, formatCostUsd } from "./format";

export type CellValue = string | number | boolean | null | undefined;

// ── CSV (§4.1) ────────────────────────────────────────────────────────────
export function csvEscapeCell(v: CellValue): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  if (/["\r\n,]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function rowsToCsv(headers: string[], rows: CellValue[][]): string {
  const lines = [headers.map(csvEscapeCell).join(",")];
  for (const row of rows) lines.push(row.map(csvEscapeCell).join(","));
  return lines.join("\r\n"); // sin CRLF final
}

// ── Markdown (§4.2) ─────────────────────────────────────────────────────────
export function mdEscapeCell(v: CellValue): string {
  if (v === null || v === undefined) return "";
  return String(v)
    .replace(/\r\n|\r|\n/g, " ")
    .replace(/\|/g, "\\|");
}

export function rowsToMarkdownTable(headers: string[], rows: CellValue[][]): string {
  const head = `| ${headers.map(mdEscapeCell).join(" | ")} |`;
  const sep = `| ${headers.map(() => "---").join(" | ")} |`;
  const body = rows.map((r) => `| ${r.map(mdEscapeCell).join(" | ")} |`);
  return [head, sep, ...body].join("\n");
}

// ── HTML (§4.11) ────────────────────────────────────────────────────────────
export function htmlEscapeCell(v: CellValue): string {
  if (v === null || v === undefined) return "";
  return String(v)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function rowsToHtmlTable(headers: string[], rows: CellValue[][]): string {
  const thead = `<thead><tr>${headers.map((h) => `<th>${htmlEscapeCell(h)}</th>`).join("")}</tr></thead>`;
  const tbody = `<tbody>${rows
    .map((r) => `<tr>${r.map((c) => `<td>${htmlEscapeCell(c)}</td>`).join("")}</tr>`)
    .join("")}</tbody>`;
  return `<table>${thead}${tbody}</table>`;
}

// ── Anti-truncado-silencioso (§4.3 C3) ──────────────────────────────────────
export function copiedRowsLabel(total: number): string {
  if (total <= 1000) return `${total} ${total === 1 ? "fila" : "filas"}`;
  return `1000 de ${total} filas; límite de copia`;
}

// ── Entidades → Markdown / Texto (§4.10 fechas ISO crudo) ────────────────────
export function ticketToMarkdown(t: Ticket): string {
  const lines = [
    `## [${t.work_item_type ?? "Ticket"} ${t.ado_id}] ${t.title}`,
    "",
    `- Estado ADO: ${t.ado_state ?? "n/d"}`,
    `- Estado Stacky: ${t.stacky_status ?? "n/d"}`,
    `- Prioridad: ${t.priority ?? "n/d"}`,
    `- Asignado: ${t.assigned_to_ado ?? "n/d"}`,
    `- Enlace: ${t.ado_url ?? adoUrl(String(t.ado_id))}`,
    "",
    t.description ?? "",
  ];
  return lines.join("\n").trimEnd();
}

export function executionToMarkdown(e: AgentExecution): string {
  const table = rowsToMarkdownTable(
    ["Campo", "Valor"],
    [
      ["Estado", e.status],
      ["Ticket", `#${e.ticket_id}${e.ticket_title ? " — " + e.ticket_title : ""}`],
      ["Proyecto", e.project ?? "n/d"],
      ["Agente", e.agent_filename ?? "n/d"],
      ["Inicio", e.started_at],
      ["Fin", e.completed_at ?? "n/d"],
      ["Duración", formatDuration(e.duration_ms ?? null)],
      ["Veredicto", e.verdict ?? "n/d"],
      ["Error", e.error_message ?? "—"],
    ],
  );
  return `## Ejecución #${e.id} — ${e.agent_type}\n\n${table}`;
}

export function executionToPlainText(e: AgentExecution): string {
  return `Ejecución #${e.id} · ${e.agent_type} · ${e.status} · ticket #${e.ticket_id}${
    e.ticket_title ? " (" + e.ticket_title + ")" : ""
  } · ${formatDuration(e.duration_ms ?? null)}`;
}

export function incidentToMarkdown(i: IncidentDTO): string {
  const bullets = [
    `- Creada: ${i.created_at}`,
    `- Estado: ${i.status}`,
    `- Ejecución: ${i.execution_id != null ? "#" + i.execution_id : "n/d"}`,
    `- Ticket: ${i.tracker_id ?? "n/d"}${i.tracker_url ? " (" + i.tracker_url + ")" : ""}`,
    `- Adjuntos: ${i.files.length}`,
  ];
  if (i.error != null) bullets.push(`- Error: ${i.error}`);
  const head = `## Incidencia ${i.id}${i.title ? " — " + i.title : ""}`;
  return `${head}\n\n${bullets.join("\n")}\n\n${i.text}`;
}

export function executionHistoryToRows(items: ExecutionHistoryItem[]): {
  headers: string[];
  csvRows: CellValue[][]; // valores crudos máquina (ISO, números)
  mdRows: CellValue[][]; // valores formateados humanos (fechas ISO §4.10)
} {
  const headers = [
    "id",
    "inicio",
    "agente",
    "runtime",
    "modelo",
    "estado",
    "duracion_ms",
    "costo_usd",
    "archivos",
    "ticket",
  ];
  const slice = items.slice(0, 1000); // §4.7 guard defensivo
  const csvRows: CellValue[][] = slice.map((it) => [
    it.id,
    it.started_at ?? "",
    it.agent_type,
    it.runtime ?? "",
    it.model ?? "",
    it.status,
    it.duration_ms,
    it.cost_usd,
    it.produced_files_count,
    it.ticket_title ?? String(it.ticket_id),
  ]);
  const mdRows: CellValue[][] = slice.map((it) => [
    it.id,
    it.started_at ?? "n/d",
    it.agent_type,
    it.runtime ?? "n/d",
    it.model ?? "n/d",
    it.status,
    formatDuration(it.duration_ms),
    it.cost_usd == null ? "n/d" : formatCostUsd(it.cost_usd),
    it.produced_files_count,
    it.ticket_title ?? String(it.ticket_id),
  ]);
  return { headers, csvRows, mdRows };
}
