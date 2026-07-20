// Plan 187 F2 — modelo puro del lote. Sin React, sin fetch, sin window.
export const BULK_MAX_LISTED_FAILURES = 5;
export const ARM_AUTO_DISARM_MS = 5000;
/** [ADICIÓN ARQUITECTO] C5 — cap de lote SOLO para acciones que DISPARAN EJECUCIONES (costo real). */
export const BULK_EXECUTION_ACTION_MAX = 25;

export interface BulkItemFailure {
  id: number;
  error: string;
}
export interface BulkResult {
  total: number;
  ok: number[];
  failed: BulkItemFailure[];
}
export type BulkWorker = (id: number) => Promise<void>;

/** Shape estructuralmente compatible con ToastState de components/Toast.tsx
 *  (se declara local para que este módulo siga siendo puro, sin imports de UI). */
export interface BulkToast {
  variant: "success" | "warning" | "error";
  title?: string;
  body: string;
}

export interface BulkRunner {
  isRunning(): boolean;
  /** null ⇔ ya hay un lote corriendo (guard anti doble-submit). Ejecuta los ids
   *  DEDUPLICADOS, EN ORDEN, SECUENCIALMENTE (await por ítem). Un throw/reject del
   *  worker se captura POR ÍTEM (try/catch) y el lote SIGUE. onProgress(done, total)
   *  se invoca tras CADA ítem (éxito o fallo). Al resolver, isRunning() vuelve a
   *  false (finally). */
  run(
    ids: number[],
    worker: BulkWorker,
    onProgress?: (done: number, total: number) => void,
  ): Promise<BulkResult> | null;
}

export function createBulkRunner(): BulkRunner {
  let running = false;
  return {
    isRunning() {
      return running;
    },
    run(ids, worker, onProgress) {
      if (running) return null;
      running = true;
      // dedup preservando el orden de aparición
      const seen = new Set<number>();
      const unique: number[] = [];
      for (const id of ids) {
        if (!seen.has(id)) {
          seen.add(id);
          unique.push(id);
        }
      }
      const total = unique.length;
      const ok: number[] = [];
      const failed: BulkItemFailure[] = [];
      const exec = async (): Promise<BulkResult> => {
        try {
          let done = 0;
          for (const id of unique) {
            try {
              await worker(id);
              ok.push(id);
            } catch (e) {
              const msg = String((e as { message?: unknown })?.message ?? e).slice(0, 200);
              failed.push({ id, error: msg });
            }
            done++;
            onProgress?.(done, total);
          }
          return { total, ok, failed };
        } finally {
          running = false;
        }
      };
      return exec();
    },
  };
}

/** Resumen agregado. Reglas EXACTAS (ver plan 187 F2). */
export function summarizeBulk(
  r: BulkResult,
  doneSingular: string,
  donePlural: string,
): BulkToast {
  if (r.total === 0) {
    return { variant: "warning", body: "Sin elementos seleccionados" };
  }
  const listed = r.failed
    .slice(0, BULK_MAX_LISTED_FAILURES)
    .map((f) => `#${f.id}`)
    .join(", ");
  const suffix = r.failed.length > BULK_MAX_LISTED_FAILURES ? "…" : "";
  if (r.failed.length === 0) {
    const word = r.ok.length === 1 ? doneSingular : donePlural;
    return { variant: "success", body: `${r.ok.length} ${word}` };
  }
  if (r.ok.length === 0) {
    return {
      variant: "error",
      title: "Falló el lote",
      body: `0 de ${r.total} — fallaron: ${listed}${suffix} · primer error: ${r.failed[0].error}`,
    };
  }
  return {
    variant: "warning",
    title: "Resultado parcial",
    body: `${r.ok.length} de ${r.total} ${donePlural} · fallaron: ${listed}${suffix}`,
  };
}

/** [ADICIÓN ARQUITECTO] C5 — freno de costo para acciones de ejecución.
 *  ids.length <= max ⇒ { ok: true }; si no ⇒ toast de advertencia. */
export function capExecutionBatch(
  ids: number[],
  max = BULK_EXECUTION_ACTION_MAX,
): { ok: true } | { ok: false; toast: BulkToast } {
  if (ids.length <= max) return { ok: true };
  return {
    ok: false,
    toast: {
      variant: "warning",
      title: "Lote demasiado grande",
      body: `Máximo ${max} relanzamientos por lote (seleccionadas: ${ids.length}). Repetí en tandas.`,
    },
  };
}

/** Armado de dos pasos: click sobre una acción destructiva.
 *  current === clicked ⇒ ejecutar (segundo click); distinto ⇒ armar (primer click). */
export function nextArmed(
  current: string | null,
  clicked: string,
): { armed: string | null; execute: boolean } {
  if (current === clicked) return { armed: null, execute: true };
  return { armed: clicked, execute: false };
}

/** Guard del Escape global: true ⇔ key === "Escape" Y el foco NO está en un campo
 *  de entrada de texto. Un <input type="checkbox"> (nuestros checkboxes de fila)
 *  NO bloquea el guard. active === null ⇒ true. */
export function shouldClearSelectionOnEscape(
  ev: { key: string },
  active: { tagName: string; isContentEditable: boolean; type?: string } | null,
): boolean {
  if (ev.key !== "Escape") return false;
  if (active === null) return true;
  if (active.isContentEditable) return false;
  const tag = active.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return false;
  if (tag === "INPUT" && active.type !== "checkbox") return false;
  return true;
}
