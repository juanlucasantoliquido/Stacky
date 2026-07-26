// Plan 176 F7 — Lógica pura del panel de verificación de cierre.
//
// Verificar re-compara el par entero: es caro y bloquea el par. Solo tiene
// sentido ofrecerlo cuando hay algo que verificar, es decir cuando el operador
// ya decidió al menos una cosa en el triage.

export interface ClosureResult {
  item_key: string;
  expectation: "resuelto" | "persiste";
  status: "ok" | "violado";
}

export interface ClosureReport {
  version: number;
  old_run_id: string | null;
  verification_run_id: string | null;
  results: ClosureResult[];
  summary: { ok: number; violado: number; sin_expectativa: number };
}

export interface TriageSummary {
  confirmado: number;
  excluido: number;
}

export function canVerify(
  runStatus: string,
  summary: TriageSummary | null | undefined
): boolean {
  if (runStatus !== "done") return false;
  if (!summary) return false;
  return (summary.confirmado ?? 0) + (summary.excluido ?? 0) > 0;
}

export function closureSummaryLabel(report: ClosureReport | null | undefined): string {
  const s = report?.summary;
  const ok = s?.ok ?? 0;
  const violado = s?.violado ?? 0;
  const sin = s?.sin_expectativa ?? 0;
  return `${ok} ok · ${violado} violados · ${sin} sin expectativa`;
}

/** Qué le pasó realmente a este ítem, en castellano y sin jerga del contrato. */
export function explainResult(result: ClosureResult): string {
  if (result.expectation === "resuelto") {
    return result.status === "ok"
      ? "Se aplicó: la diferencia ya no está."
      : "Seguía pendiente: confirmaste migrarlo y la diferencia sigue ahí.";
  }
  return result.status === "ok"
    ? "Intacto: lo excluiste y sigue difiriendo, como corresponde."
    : "Se tocó algo excluido: la diferencia desapareció y no debía.";
}

/** Los violados primero: es lo único que exige una acción. */
export function sortForDisplay(results: ClosureResult[]): ClosureResult[] {
  return [...(results ?? [])].sort((a, b) => {
    if (a.status !== b.status) return a.status === "violado" ? -1 : 1;
    return a.item_key.localeCompare(b.item_key);
  });
}
