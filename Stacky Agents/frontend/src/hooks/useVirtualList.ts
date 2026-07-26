import { useCallback, useRef, useState } from "react";

import {
  computeVirtualWindow,
  deriveIsVirtualized,
  type VirtualWindow,
} from "../utils/virtualWindow";

export interface UseVirtualListOptions {
  total: number;
  rowHeightPx: number;
  /** El flag CRUDO. El umbral lo aplica el hook: si cada call site lo aplicara
   *  por su cuenta, alguno se lo saltearía y virtualizaría una lista de 12. */
  enabled: boolean;
  overscan?: number;
  /** Plan 172 — la fila con foco no puede caerse del DOM. */
  pinnedIndex?: number | null;
}

export interface UseVirtualListResult extends VirtualWindow {
  isVirtualized: boolean;
  containerRef: React.MutableRefObject<HTMLDivElement | null>;
  onScroll: () => void;
  scrollToIndex: (i: number) => void;
}

/** Plan 174 F1 — Renderizar solo lo que se ve. Wiring fino: la decisión vive en
 *  `utils/virtualWindow.ts`, testeada aparte. */
export function useVirtualList(opts: UseVirtualListOptions): UseVirtualListResult {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [scrollTopPx, setScrollTopPx] = useState(0);
  const [viewportHeightPx, setViewportHeightPx] = useState(600);
  const frameRef = useRef<number | null>(null);

  const isVirtualized = deriveIsVirtualized(opts.total, opts.enabled);

  const onScroll = useCallback(() => {
    if (!isVirtualized) return;
    // Un recomputo por frame como máximo: sin esto el scroll dispara decenas de
    // renders por segundo y la lista se siente PEOR que sin virtualizar.
    if (frameRef.current != null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      const nodo = containerRef.current;
      if (!nodo) return;
      setScrollTopPx(nodo.scrollTop);
      setViewportHeightPx(nodo.clientHeight || 600);
    });
  }, [isVirtualized]);

  const scrollToIndex = useCallback(
    (i: number) => {
      const nodo = containerRef.current;
      if (nodo) nodo.scrollTop = Math.max(0, i) * opts.rowHeightPx;
    },
    [opts.rowHeightPx],
  );

  if (!isVirtualized) {
    return {
      start: 0,
      end: opts.total,
      padTopPx: 0,
      padBottomPx: 0,
      rendered: opts.total,
      isVirtualized: false,
      containerRef,
      onScroll: () => {},
      scrollToIndex,
    };
  }

  const ventana = computeVirtualWindow({
    total: opts.total,
    rowHeightPx: opts.rowHeightPx,
    viewportHeightPx,
    scrollTopPx,
    overscan: opts.overscan,
    pinnedIndex: opts.pinnedIndex,
  });

  return { ...ventana, isVirtualized: true, containerRef, onScroll, scrollToIndex };
}

export default useVirtualList;
