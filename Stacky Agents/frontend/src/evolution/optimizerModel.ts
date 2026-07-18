// Plan 169 F5 — modelo puro del Optimizador evolutivo (funciones puras, sin RTL/jsdom).
// Espejo estructural de fitnessModel.ts del 168.

export type RunStatus =
  | "running"
  | "completed"
  | "no_improvement"
  | "stopped_budget"
  | "cancelled"
  | "error";

export type Verdict = "base" | "winner" | "pareto" | "dominated" | "invalid";

export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

export interface OptimizerTargetDto {
  target_ref: string;
  aspect_key: string;
  cases_enabled: number;
  last_score: number | null;
}

export interface OptimizationRunDto {
  id: string;
  aspect_key: string;
  target_ref: string;
  status: RunStatus;
  error: string | null;
  cancel_requested: boolean;
  generator: { mode: string; runtime: string | null; model: string | null };
  variants_planned: number;
  variants_done: number;
  base: { score: number | null; cost_proxy: number } | null;
  winner: { score: number | null; cost_proxy: number } | null;
  proposal_id: string | null;
  margin_used: number;
  budget: { limit_tokens: number; tokens_est_in: number; tokens_est_out: number; exhausted: boolean };
  steps: { ts: string; text: string }[];
  started_at: string;
  finished_at: string | null;
}

export interface ArchiveEntryDto {
  id: string;
  run_id: string;
  parent_id: string | null;
  kind: "base" | "variant";
  verdict: Verdict;
  invalid_reason: string | null;
  fitness: { score: number | null; deterministic_gate: string } | null;
  cost_proxy: number;
  mutation_lesson: string | null;
  generator_model: string | null;
  created_at: string;
}

export const RUN_POLL_MS = 2000; // §F5: intervalo del setTimeout encadenado
export const RUN_POLL_MAX = 900; // tope duro: 900 * 2 s = 30 min

export function runStatusTone(s: RunStatus): Tone {
  switch (s) {
    case "running":
      return "info";
    case "completed":
      return "success";
    case "stopped_budget":
      return "warning";
    case "error":
      return "danger";
    case "no_improvement":
    case "cancelled":
    default:
      return "neutral";
  }
}

export function runStatusLabel(s: RunStatus): string {
  switch (s) {
    case "running":
      return "Corriendo";
    case "completed":
      return "Propuesta emitida";
    case "no_improvement":
      return "Sin mejora suficiente";
    case "stopped_budget":
      return "Presupuesto agotado";
    case "cancelled":
      return "Cancelada";
    case "error":
      return "Error";
    default:
      return s;
  }
}

export function verdictTone(v: Verdict): Tone {
  switch (v) {
    case "winner":
      return "success";
    case "pareto":
      return "info";
    case "invalid":
      return "danger";
    case "base":
    case "dominated":
    default:
      return "neutral";
  }
}

export function verdictLabel(v: Verdict): string {
  switch (v) {
    case "base":
      return "Base";
    case "winner":
      return "Ganadora";
    case "pareto":
      return "Frente Pareto";
    case "dominated":
      return "Dominada";
    case "invalid":
      return "Inválida";
    default:
      return v;
  }
}

export function generatorLabel(g: { mode: string; runtime: string | null }): string {
  if (g.mode === "local") return "Modelo local";
  if (g.mode === "runtime") return `Runtime: ${g.runtime}`;
  return g.mode;
}

export function isTerminal(s: RunStatus): boolean {
  return s !== "running";
}

export function lineageRows(
  entries: ArchiveEntryDto[],
): { entry: ArchiveEntryDto; depth: number }[] {
  const byCreated = (a: ArchiveEntryDto, b: ArchiveEntryDto) =>
    (a.created_at || "").localeCompare(b.created_at || "");
  const bases = entries.filter((e) => e.kind === "base").slice().sort(byCreated);
  const rows: { entry: ArchiveEntryDto; depth: number }[] = [];
  const placed = new Set<string>();
  for (const base of bases) {
    rows.push({ entry: base, depth: 0 });
    const children = entries.filter((e) => e.parent_id === base.id).slice().sort(byCreated);
    for (const ch of children) {
      rows.push({ entry: ch, depth: 1 });
      placed.add(ch.id);
    }
  }
  const orphans = entries
    .filter((e) => e.kind !== "base" && !placed.has(e.id))
    .slice()
    .sort(byCreated);
  for (const o of orphans) rows.push({ entry: o, depth: 0 });
  return rows;
}

export function improvementDisplay(base: number | null, winner: number | null): string {
  if (base === null || base === undefined || winner === null || winner === undefined) return "—";
  return `${base.toFixed(2)} → ${winner.toFixed(2)}`;
}
