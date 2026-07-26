// Plan 176 F8 — Export del diff FILTRADO a CSV y JSON.
//
// Se exporta lo que el operador está viendo, no el diff entero: si filtró por
// severidad y exporta las 800 filas completas, el archivo no coincide con la
// pantalla y ahí empieza la desconfianza.

import type { DiffItem } from "./dbcompareTypes";
import { decisionFor, type TriageDoc } from "./triageLogic";

const COLUMNS = [
  "object_type",
  "schema",
  "name",
  "action",
  "severity",
  "changes",
  "decision",
] as const;

/** Un campo con coma, comilla o salto de línea rompe el CSV si no se escapa.
 *  Los nombres de objeto de BD pueden traer cualquiera de los tres. */
export function csvEscape(value: unknown): string {
  const s = value == null ? "" : String(value);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function toCsv(items: DiffItem[], triage?: TriageDoc | null): string {
  const filas = [COLUMNS.join(",")];
  for (const item of items ?? []) {
    filas.push(
      [
        item.object_type,
        item.schema,
        item.name,
        item.action,
        item.severity,
        (item.changes ?? []).map((c) => c.kind).join(" | "),
        decisionFor(triage, item.item_key),
      ]
        .map(csvEscape)
        .join(",")
    );
  }
  // Terminar en salto: varias herramientas ignoran la última línea sin él.
  return filas.join("\n") + "\n";
}

export function toJson(items: DiffItem[], triage?: TriageDoc | null): string {
  return JSON.stringify(
    (items ?? []).map((item) => ({
      object_type: item.object_type,
      schema: item.schema,
      name: item.name,
      action: item.action,
      severity: item.severity,
      changes: (item.changes ?? []).map((c) => c.kind),
      item_key: item.item_key ?? null,
      decision: decisionFor(triage, item.item_key),
    })),
    null,
    2
  );
}

/** Nombre con el run_id adentro: dos exports de corridas distintas no pueden
 *  llamarse igual en la carpeta de descargas. */
export function exportFilename(runId: string, ext: "csv" | "json"): string {
  const limpio = String(runId || "run").replace(/[^A-Za-z0-9._-]/g, "_");
  return `${limpio}-diff.${ext}`;
}

export function mimeFor(ext: "csv" | "json"): string {
  return ext === "csv" ? "text/csv;charset=utf-8" : "application/json;charset=utf-8";
}
