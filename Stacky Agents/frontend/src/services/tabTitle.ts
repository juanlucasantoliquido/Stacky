/**
 * Dueño ÚNICO de document.title (plan 134 F3). Reemplaza el flash de 4 s de
 * executionNotifier, que podía dejar el título pegado en "🤖 done — …" para
 * siempre si dos fines de run llegaban separados por 1.5–4 s (el revert tardío
 * re-instalaba un título ya flasheado). Acá el título se DERIVA del estado y el
 * título base se captura UNA sola vez, así ningún reorden de eventos lo corrompe.
 */
import { combineOutcome, computeTabTitle, type FinishOutcome } from "./notifierCore";

let baseTitle: string | null = null;
let activeCount = 0;
let lastOutcome: FinishOutcome = null;

function apply(): void {
  if (baseTitle == null) return;
  const next = computeTabTitle(activeCount, lastOutcome, baseTitle);
  if (document.title !== next) document.title = next;
}

/** Captura el título base una sola vez (idempotente — seguro ante StrictMode/HMR). */
export function initTabTitle(): void {
  if (baseTitle == null) baseTitle = document.title;
}

export function setActiveRunCount(n: number): void {
  initTabTitle();
  activeCount = Math.max(0, n);
  apply();
}

export function reportRunOutcome(status: string): void {
  initTabTitle();
  lastOutcome = combineOutcome(lastOutcome, status);
  apply();
}

/** El operador volvió a mirar la pestaña: limpiar el desenlace persistente. */
export function clearOutcome(): void {
  if (lastOutcome == null) return;
  lastOutcome = null;
  apply();
}
