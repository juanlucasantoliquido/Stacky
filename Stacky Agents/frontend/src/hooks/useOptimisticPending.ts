import { useCallback, useState } from "react";

/**
 * Plan 143 F6 — feedback óptimista LOCAL y EFÍMERO para UNA acción en vuelo.
 * NO reemplaza las señales persistentes de runs (plan 134) ni el surfacing de errores
 * (plan 135): es solo el estado visual "encolando/guardando" mientras dura una promesa.
 * Presentación pura, sin backend.
 *
 * CONTRATO DEL ADOPTANTE (C5): la promesa `op()` DEBE resolver O rechazar. `run` des-marca
 * `pending` en `finally`, así que un éxito o un error revierten el estado óptimista y liberan el
 * control (`.u-pending` vuelve a interactivo). Pero una promesa que NUNCA settlea dejaría el
 * control atenuado + `pointer-events: none` para siempre (soft-lock). Si la acción puede colgarse,
 * el adoptante DEBE imponer un timeout/AbortController antes de pasarla a `run`.
 * `run` re-lanza el error (no lo traga): el surfacing lo hace el plan 135, no este hook.
 */
export interface OptimisticPending {
  /** true mientras la operación envuelta está en vuelo. */
  pending: boolean;
  /** Envuelve una promesa: marca pending mientras corre; SIEMPRE la des-marca al terminar. */
  run: <T>(op: () => Promise<T>) => Promise<T>;
  /** Clase CSS a aplicar cuando pending: "u-pending" (plan 143) o "" cuando no. */
  pendingClass: string;
}

/** Lógica pura, testeable sin React. */
export async function runWithPending<T>(
  setPending: (v: boolean) => void,
  op: () => Promise<T>,
): Promise<T> {
  setPending(true);
  try {
    return await op();
  } finally {
    setPending(false);
  }
}

export function useOptimisticPending(): OptimisticPending {
  const [pending, setPending] = useState(false);
  const run = useCallback(
    <T,>(op: () => Promise<T>): Promise<T> => runWithPending(setPending, op),
    [],
  );
  return { pending, run, pendingClass: pending ? "u-pending" : "" };
}

export default useOptimisticPending;
