// Plan 124 — Comparador de BD: hook de polling de una corrida comparativa (doc 123 §F2/§F3).
//
// PENDIENTE: el fetch de acá apunta directo a la URL literal del endpoint (`GET
// /api/db-compare/runs/<id>`, doc 123 §F3) en vez de pasar por `DbCompare.getRun` del
// namespace de `frontend/src/api/endpoints.ts`, porque ese namespace no existe todavía en
// esta rama (Plan 122 no mergeado — ver F0 del doc del plan). Cuando 122/123 se mergeen,
// reemplazar el `fetch` inline por `DbCompare.getRun(runId)`.
import { useEffect, useRef, useState } from "react";
import type { CompareRun } from "./dbcompareTypes";

/** Un status de run es terminal cuando ya no tiene sentido seguir haciendo polling. */
export function isTerminal(status: string): boolean {
  return status === "done" || status === "error";
}

/**
 * Backoff fijo por escalones (doc 124 §F1, fronteras ajustadas por FIX C5 de la crítica v2):
 * elapsedMs < 10000 -> 1000ms; elapsedMs < 60000 -> 2000ms; si no -> 5000ms.
 */
export function nextPollDelayMs(elapsedMs: number): number {
  if (elapsedMs < 10000) return 1000;
  if (elapsedMs < 60000) return 2000;
  return 5000;
}

export interface UseCompareRunResult {
  run: CompareRun | null;
  error: string | null;
}

export function useCompareRun(runId: string | null): UseCompareRunResult {
  const [run, setRun] = useState<CompareRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startRef = useRef<number>(Date.now());

  useEffect(() => {
    if (!runId) {
      setRun(null);
      setError(null);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    startRef.current = Date.now();

    const poll = async (): Promise<void> => {
      try {
        const res = await fetch(`/api/db-compare/runs/${encodeURIComponent(runId)}`);
        const data = (await res.json()) as { ok: boolean; run?: CompareRun; error?: string };
        if (cancelled) return;
        if (!data.ok || !data.run) {
          setError(data.error ?? "No se pudo obtener la corrida.");
          return;
        }
        setRun(data.run);
        setError(null);
        if (!isTerminal(data.run.status)) {
          const elapsed = Date.now() - startRef.current;
          timer = setTimeout(poll, nextPollDelayMs(elapsed));
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      }
    };

    void poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

  return { run, error };
}
