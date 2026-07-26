// Plan 174 F1 — Qué filas hace falta renderizar de una lista larga. PURO.
//
// Por debajo del umbral NO se virtualiza: renderizar de más cuesta unos ms, pero
// virtualizar una lista corta rompe el Ctrl+F del navegador, que es una función
// que el operador usa todo el tiempo y que nadie pidió cambiar.

export const VIRTUALIZATION_THRESHOLD = 200;
export const DEFAULT_OVERSCAN = 10;

export interface VirtualWindowInput {
  total: number;
  rowHeightPx: number;
  viewportHeightPx: number;
  scrollTopPx: number;
  overscan?: number;
  /** Índice que DEBE quedar dentro de la ventana (foco roving del plan 172). */
  pinnedIndex?: number | null;
}

export interface VirtualWindow {
  /** Primer índice renderizado, inclusive. */
  start: number;
  /** Último índice renderizado, EXCLUSIVE: `slice(start, end)`. */
  end: number;
  padTopPx: number;
  padBottomPx: number;
  rendered: number;
}

export function computeVirtualWindow(input: VirtualWindowInput): VirtualWindow {
  const total = Math.max(0, Math.floor(input?.total ?? 0));
  const rowHeightPx = Math.max(0, input?.rowHeightPx ?? 0);
  const viewportHeightPx = Math.max(0, input?.viewportHeightPx ?? 0);
  const scrollTopPx = Math.max(0, input?.scrollTopPx ?? 0);
  const overscan = Math.max(0, input?.overscan ?? DEFAULT_OVERSCAN);

  if (total === 0 || rowHeightPx <= 0) {
    return { start: 0, end: total, padTopPx: 0, padBottomPx: 0, rendered: total };
  }

  const firstVisible = Math.min(
    Math.max(0, Math.floor(scrollTopPx / rowHeightPx)),
    Math.max(0, total - 1),
  );
  // +1 por la fila que asoma a medias en el borde inferior.
  const visibleCount = Math.ceil(viewportHeightPx / rowHeightPx) + 1;

  let start = Math.max(0, firstVisible - overscan);
  let end = Math.min(total, firstVisible + visibleCount + overscan);

  // La fila con foco no puede desaparecer del DOM: si se desmonta, el navegador
  // manda el foco al body y el operador pierde dónde estaba.
  const pinned = input?.pinnedIndex;
  if (pinned != null && pinned >= 0 && pinned < total) {
    start = Math.min(start, pinned);
    end = Math.max(end, pinned + 1);
  }

  return {
    start,
    end,
    padTopPx: start * rowHeightPx,
    padBottomPx: (total - end) * rowHeightPx,
    rendered: end - start,
  };
}

export function shouldVirtualize(total: number, flagEnabled: boolean): boolean {
  return Boolean(flagEnabled) && total >= VIRTUALIZATION_THRESHOLD;
}

/** La decisión de virtualizar pasa SIEMPRE por el umbral: no existe un modo
 *  "flag cruda sin umbral". Tenerlo en un solo lugar evita que un call site lo
 *  saltee y virtualice una lista de 12 filas. */
export function deriveIsVirtualized(total: number, flagEnabled: boolean): boolean {
  return shouldVirtualize(total, flagEnabled);
}
