// Plan 266 — Forma garantizada del summary del Comparador de BD.
// ÚNICA fuente de verdad: ningún componente de dbcompare/ puede leer by_severity /
// by_action / by_object_type sin pasar por acá (lo verifica el ratchet
// src/__tests__/dbcompareSummaryShapeRatchet.test.ts).
//
// NOTA DE IMPLEMENTACIÓN (no cosmética): este módulo lee las claves con corchetes y
// literal de string — src["by_severity"] — y NUNCA con punto. Así el archivo no
// contiene el patrón que su propio ratchet prohíbe y no necesita estar en su allowlist.
import type { Severity, DiffAction, ObjectType, DiffSummary } from "./dbcompareTypes";

export const EMPTY_BY_SEVERITY: Record<Severity, number> = Object.freeze({
  info: 0,
  warn: 0,
  danger: 0,
});
export const EMPTY_BY_ACTION: Record<DiffAction, number> = Object.freeze({
  added: 0,
  removed: 0,
  changed: 0,
});
export const EMPTY_BY_OBJECT_TYPE: Record<ObjectType, number> = Object.freeze({
  table: 0,
  view: 0,
  sequence: 0,
});

function asRecord(raw: unknown): Record<string, unknown> {
  return raw !== null && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
}

// Plan 266 C16/C21 — solo decimales. Number() acepta 0x/0b/0o y float() de Python
// acepta "1_0": sin este guard los dos lados divergen (medido: "0x10" -> 16 en TS
// / 0 en Python; "1_0" -> NaN en TS / 10.0 en Python). Gemela EXACTA de
// _DECIMAL_RE en dbcompare_runs.py (F3): si cambia una, cambia la otra — lo
// verifica la tabla de verdad compartida de F1.5.
const DECIMAL_RE = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;

export function toCount(value: unknown): number {
  const n = typeof value === "number" ? value
          : typeof value === "string" ? (DECIMAL_RE.test(value.trim()) ? Number(value) : NaN)
          : NaN;
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.floor(n);
}

export function toScore(value: unknown): number {
  const n = typeof value === "number" ? value
          : typeof value === "string" ? (DECIMAL_RE.test(value.trim()) ? Number(value) : NaN)
          : NaN;
  if (!Number.isFinite(n)) return 0;
  return Math.min(100, Math.max(0, Math.round(n * 10) / 10));
}

export function safeBySeverity(raw: unknown): Record<Severity, number> {
  const src = asRecord(raw);
  return { info: toCount(src["info"]), warn: toCount(src["warn"]), danger: toCount(src["danger"]) };
}

export function safeByAction(raw: unknown): Record<DiffAction, number> {
  const src = asRecord(raw);
  return {
    added: toCount(src["added"]),
    removed: toCount(src["removed"]),
    changed: toCount(src["changed"]),
  };
}

export function safeByObjectType(raw: unknown): Record<ObjectType, number> {
  const src = asRecord(raw);
  return {
    table: toCount(src["table"]),
    view: toCount(src["view"]),
    sequence: toCount(src["sequence"]),
  };
}

export function safeSummary(raw: unknown): DiffSummary {
  const src = asRecord(raw);
  return {
    by_severity: safeBySeverity(src["by_severity"]),
    by_action: safeByAction(src["by_action"]),
    by_object_type: safeByObjectType(src["by_object_type"]),
    objects_total: toCount(src["objects_total"]),
    objects_unchanged: toCount(src["objects_unchanged"]),
    parity_score: toScore(src["parity_score"]),
  };
}
