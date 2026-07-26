// Plan 176 F5 — Lógica pura del panel de precondiciones.
//
// Las gates son consultas SELECT derivadas del diff: contar NULLs antes de un
// NOT NULL, buscar duplicados antes de una PK. Ejecutarlas es SIEMPRE un click
// del operador — nada acá se dispara solo.

export type GateCheck = "expect_zero" | "info_rowcount";
export type GateStatus = "pass" | "fail" | "error" | "info";

export interface Gate {
  gate_id: string;
  item_key: string;
  kind: string;
  description: string;
  sql: string;
  check: GateCheck;
  target_alias: string;
}

export interface GateResult {
  status: GateStatus;
  value: number | null;
  detail: string;
  checked_at: string;
}

/** Sin resultado todavía: distinto de "pasó" y distinto de "falló". */
export function statusOf(
  results: Record<string, GateResult> | null | undefined,
  gateId: string
): GateStatus | "sin_correr" {
  return results?.[gateId]?.status ?? "sin_correr";
}

export function statusLabel(status: GateStatus | "sin_correr"): string {
  switch (status) {
    case "pass":
      return "✔ Sin bloqueos";
    case "fail":
      return "✖ Bloquea";
    case "error":
      return "⚠ No se pudo verificar";
    case "info":
      return "ℹ Informativo";
    default:
      return "— Sin correr";
  }
}

export function statusClass(status: GateStatus | "sin_correr"): string {
  switch (status) {
    case "pass":
      return "gatePass";
    case "fail":
      return "gateFail";
    case "error":
      return "gateError";
    case "info":
      return "gateInfo";
    default:
      return "gatePending";
  }
}

export function summarizeGates(
  gates: Gate[] | null | undefined,
  results: Record<string, GateResult> | null | undefined
): { total: number; pass: number; fail: number; error: number; sinCorrer: number } {
  const lista = gates ?? [];
  const conteo = { total: lista.length, pass: 0, fail: 0, error: 0, sinCorrer: 0 };
  for (const g of lista) {
    const s = statusOf(results, g.gate_id);
    if (s === "pass") conteo.pass += 1;
    else if (s === "fail") conteo.fail += 1;
    else if (s === "error") conteo.error += 1;
    else if (s === "sin_correr") conteo.sinCorrer += 1;
    // "info" no entra en ningún contador de veredicto: no hay valor correcto.
  }
  return conteo;
}

/**
 * El titular del panel. Un `fail` manda sobre todo lo demás: es lo único que
 * significa "si migrás ahora, el ALTER va a fallar".
 */
export function headlineFor(
  gates: Gate[] | null | undefined,
  results: Record<string, GateResult> | null | undefined
): string {
  const s = summarizeGates(gates, results);
  if (!s.total) return "Este diff no requiere precondiciones.";
  if (s.fail > 0) {
    return s.fail === 1
      ? "1 precondición bloquea la migración."
      : `${s.fail} precondiciones bloquean la migración.`;
  }
  if (s.sinCorrer === s.total) return "Precondiciones sin verificar.";
  if (s.error > 0) return "Algunas precondiciones no se pudieron verificar.";
  return "Todas las precondiciones dan verde.";
}

/** Los bloqueantes primero: es lo único que exige una acción antes de migrar. */
export function sortForDisplay(
  gates: Gate[] | null | undefined,
  results: Record<string, GateResult> | null | undefined
): Gate[] {
  const peso = (g: Gate) => {
    const s = statusOf(results, g.gate_id);
    if (s === "fail") return 0;
    if (s === "error") return 1;
    if (s === "sin_correr") return 2;
    return 3;
  };
  return [...(gates ?? [])].sort(
    (a, b) => peso(a) - peso(b) || a.gate_id.localeCompare(b.gate_id)
  );
}

/** Solo tiene sentido ofrecer "verificar" sobre un diff terminado y con gates. */
export function canEvaluate(
  runStatus: string | null | undefined,
  gatesEnabled: boolean | null | undefined,
  gates: Gate[] | null | undefined
): boolean {
  return runStatus === "done" && Boolean(gatesEnabled) && (gates?.length ?? 0) > 0;
}
