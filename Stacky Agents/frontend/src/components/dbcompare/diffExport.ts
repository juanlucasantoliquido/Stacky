// Plan 176 F8 — Export del diff FILTRADO a CSV y JSON.
//
// Se exporta lo que el operador está viendo, no el diff entero: si filtró por
// severidad y exporta las 800 filas completas, el archivo no coincide con la
// pantalla y ahí empieza la desconfianza.

import type { DiffItem } from "./dbcompareTypes";

/** Orden literal de columnas. Cambiarlo rompe las planillas que ya armó el
 *  operador sobre exports anteriores. */
const COLUMNS = ["object_type", "schema", "name", "action", "severity", "kinds"] as const;

/** Quoting RFC 4180: un campo con coma, comilla o salto de línea rompe el CSV si
 *  no se envuelve. Los nombres de objeto de BD pueden traer los tres. */
export function csvEscape(value: unknown): string {
  const s = value == null ? "" : String(value);
  if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

/** CSV RFC 4180: separador de filas CRLF, sin BOM. */
export function toCsv(items: DiffItem[]): string {
  const filas = [COLUMNS.join(",")];
  for (const item of items ?? []) {
    filas.push(
      [
        item.object_type,
        item.schema,
        item.name,
        item.action,
        item.severity,
        (item.changes ?? []).map((c) => c.kind).join("|"),
      ]
        .map(csvEscape)
        .join(",")
    );
  }
  return filas.join("\r\n") + "\r\n";
}

/** Los ítems tal cual: el JSON es para reprocesar, no para leer a ojo, así que
 *  no se recorta ningún campo. */
export function toJson(items: DiffItem[]): string {
  return JSON.stringify(items ?? [], null, 2);
}

/** Nombre con el run_id adentro: dos exports de corridas distintas no pueden
 *  llamarse igual en la carpeta de descargas. */
export function exportFilename(runId: string, ext: "csv" | "json"): string {
  const limpio = String(runId || "run").replace(/[^A-Za-z0-9._-]/g, "_");
  return `diff_${limpio}.${ext}`;
}

export function mimeFor(ext: "csv" | "json"): string {
  return ext === "csv" ? "text/csv;charset=utf-8" : "application/json;charset=utf-8";
}
