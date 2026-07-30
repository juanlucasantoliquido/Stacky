/**
 * Plan 265 F3 — Cancelar y volver a lanzar, con confirmación. Lógica pura.
 *
 * ADVERTENCIA (D1/E2, no negociable): esta consola cancela EXCLUSIVAMENTE por
 * el camino de `Executions` en api/endpoints.ts, que valida el estado y
 * devuelve 409 si no es cancelable, y despacha al runner que corresponda.
 * Existe OTRO objeto en ese mismo archivo con una función del mismo nombre
 * que pega en un endpoint de agentes sin ningún gate de estado y sin matar el
 * subproceso — ese otro camino está PROHIBIDO en todo este módulo y en el
 * resto de los servicios "console*" (el test 11 de F3 lo verifica leyendo el
 * texto fuente). Ver F3 del plan 265 para el detalle completo.
 */
import { capabilitiesFor, normalizeRuntime } from "./consoleCapabilities";

export type ConsoleActionId = "cancel" | "relaunch" | "copyAll" | "close";

export interface ExecutionSnapshot {
  status: string | null; // "running" | "completed" | "error" | "cancelled" | ...
  runtime: string | null; // metadata.runtime crudo; se normaliza con consoleCapabilities
  hasOrigin: boolean;
}

/** Estados que el backend acepta cancelar. Espejo EXACTO de
 *  api/executions.py:695 (`if row.status not in (...)`, re-verificado F0.0
 *  2026-07-29). Si cambia allá, este set y su test cambian acá: son un contrato. */
export const CANCELLABLE_STATUSES: ReadonlySet<string> = new Set([
  "vscode_chat",
  "preparing",
  "queued",
  "running",
]);

/** Qué acciones se ofrecen y cuáles quedan deshabilitadas (con motivo). Nunca lanza.
 *  El motivo de `cancel` sale de consoleCapabilities.capabilitiesFor(...).cancel.note. */
export function availableActions(
  snap: ExecutionSnapshot,
): Array<{ id: ConsoleActionId; enabled: boolean; reason: string | null }> {
  const status = snap?.status ?? null;
  const runtime = normalizeRuntime(snap?.runtime ?? null);
  const hasOrigin = snap?.hasOrigin === true;
  const caps = capabilitiesFor(runtime, { hasOrigin });

  const cancelCancellable = status !== null && CANCELLABLE_STATUSES.has(status);
  const cancelEnabled = cancelCancellable && caps.cancel.supported;
  const cancelReason = cancelEnabled
    ? caps.cancel.note
    : cancelCancellable
      ? caps.cancel.note
      : "Esta ejecución ya no está en un estado cancelable.";

  return [
    { id: "cancel", enabled: cancelEnabled, reason: cancelReason },
    {
      id: "relaunch",
      enabled: caps.relaunch.supported,
      reason: caps.relaunch.note,
    },
    { id: "copyAll", enabled: true, reason: null },
    { id: "close", enabled: true, reason: null },
  ];
}

/** ¿Esta acción exige confirmación explícita antes de ejecutarse? */
export function requiresConfirmation(id: ConsoleActionId): boolean {
  return id === "cancel";
}

/** Texto exacto del diálogo de confirmación. */
export function confirmationText(id: ConsoleActionId, executionId: number): string {
  if (id === "cancel") {
    return `¿Cancelar la ejecución #${executionId}? Se detendrá la sesión del agente.`;
  }
  return `¿Confirmar "${id}" sobre la ejecución #${executionId}?`;
}
