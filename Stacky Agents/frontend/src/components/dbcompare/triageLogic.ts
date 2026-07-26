// Plan 176 F2 — Lógica pura del triage del diff.
//
// El operador cura el diff donde lo está mirando, en vez de anotar en un
// markdown externo qué migrar y qué no.
//
// La `item_key` la emite SIEMPRE el backend (campo aditivo `item.item_key`).
// Acá NO se deriva: el enmascarado del plan 181 tapa los valores de PK de las
// filas de datos, así que el frontend no podría calcularla ni queriendo.

export type TriageDecision = "confirmado" | "excluido" | "pendiente";

export interface TriageEntry {
  decision: TriageDecision;
  note?: string;
  decided_at?: string;
}

export interface TriageDoc {
  version?: number;
  run_id?: string;
  items?: Record<string, TriageEntry>;
  updated_at?: string | null;
  summary?: { confirmado: number; excluido: number; pendiente: number } | null;
}

/** Ausente = pendiente. No decidir es un estado válido, no un dato faltante. */
export function decisionFor(
  triage: TriageDoc | null | undefined,
  itemKey: string | null | undefined
): TriageDecision {
  if (!itemKey) return "pendiente";
  const entrada = triage?.items?.[itemKey];
  return entrada?.decision ?? "pendiente";
}

export function noteFor(
  triage: TriageDoc | null | undefined,
  itemKey: string | null | undefined
): string {
  if (!itemKey) return "";
  return triage?.items?.[itemKey]?.note ?? "";
}

/** Orden literal: pendiente → confirmado → excluido → pendiente. */
export function cycleDecision(current: TriageDecision): TriageDecision {
  if (current === "pendiente") return "confirmado";
  if (current === "confirmado") return "excluido";
  return "pendiente";
}

export function summarizeTriage(
  triage: TriageDoc | null | undefined,
  totalItems: number
): { confirmado: number; excluido: number; pendiente: number } {
  const decisiones = Object.values(triage?.items ?? {}).map((e) => e.decision);
  const confirmado = decisiones.filter((d) => d === "confirmado").length;
  const excluido = decisiones.filter((d) => d === "excluido").length;
  return {
    confirmado,
    excluido,
    // Si el diff encogió entre corridas, un pendiente negativo sería mentira.
    pendiente: Math.max(0, (totalItems || 0) - confirmado - excluido),
  };
}

export function decisionBadgeClass(d: TriageDecision): string {
  if (d === "confirmado") return "triageConfirmado";
  if (d === "excluido") return "triageExcluido";
  return "triagePendiente";
}

export function decisionLabel(d: TriageDecision): string {
  if (d === "confirmado") return "✔ Confirmado";
  if (d === "excluido") return "✖ Excluido";
  return "— Pendiente";
}

/** Qué significa la decisión para lo que va a pasar. El operador decide mejor
 *  si sabe la consecuencia, no solo el nombre del estado. */
export function decisionHelp(d: TriageDecision): string {
  if (d === "confirmado") return "Se va a migrar: emite script y su backup.";
  if (d === "excluido") return "NO se migra: no emite script ni backup.";
  return "Sin decidir: se migra igual (el default es migrar todo).";
}

/** Solo se puede curar un diff terminado y con la capacidad encendida. */
export function canTriage(
  runStatus: string | null | undefined,
  triageEnabled: boolean | null | undefined
): boolean {
  return runStatus === "done" && Boolean(triageEnabled);
}

export function hasAnyDecision(triage: TriageDoc | null | undefined): boolean {
  return Object.keys(triage?.items ?? {}).length > 0;
}
