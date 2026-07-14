// Plan 124 — Comparador de BD: lógica pura del stepper de progreso (doc §F2).
import type { CompareRun, RunPhase } from "./dbcompareTypes";

export const PHASE_ORDER: RunPhase[] = ["queued", "snapshot_source", "snapshot_target", "diff", "done"];

export type PhaseState = "pending" | "active" | "done";

/**
 * Estado visual de un paso del stepper para la corrida actual.
 * Cuando el run ya llegó a "done", TODOS los pasos se muestran "done" (terminal).
 */
export function phaseState(run: CompareRun, phase: RunPhase): PhaseState {
  if (run.phase === "done") return "done";
  const idx = PHASE_ORDER.indexOf(phase);
  const currentIdx = PHASE_ORDER.indexOf(run.phase);
  if (idx < currentIdx) return "done";
  if (idx === currentIdx) return "active";
  return "pending";
}
