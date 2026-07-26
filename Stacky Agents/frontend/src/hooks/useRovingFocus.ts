import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, MutableRefObject } from "react";

import {
  clampRovingIndex,
  nextRovingIndex,
  rovingActionForKey,
} from "../services/rovingFocus";
import { isUiShortcutsEnabled } from "../services/shortcuts";

interface UseRovingFocusOpts {
  itemCount: number;
  onOpen: (index: number) => void;
  onEscape?: () => void;
}

/**
 * Plan 172 F4 — Recorrer una tabla con el teclado sin tocar el mouse.
 *
 * Pegamento fino: toda la decisión vive en `services/rovingFocus.ts`, testeado
 * aparte. Acá solo está lo que necesita el DOM.
 */
export function useRovingFocus(opts: UseRovingFocusOpts): {
  activeIndex: number;
  containerProps: {
    onKeyDown: (ev: ReactKeyboardEvent) => void;
    ref: MutableRefObject<HTMLTableSectionElement | null>;
  };
  rowProps: (index: number) => {
    tabIndex: number;
    "data-roving-item": string;
    onFocus: () => void;
  };
} {
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLTableSectionElement | null>(null);

  // Si la lista encoge (borrado, paginación), el índice tiene que seguirla o
  // queda apuntando a una fila que ya no existe.
  useEffect(() => {
    setActiveIndex((i) => clampRovingIndex(i, opts.itemCount));
  }, [opts.itemCount]);

  const onKeyDown = useCallback(
    (ev: ReactKeyboardEvent) => {
      if (!isUiShortcutsEnabled()) return;
      // Solo se secuestran las teclas cuando el foco está en la FILA. Si está en
      // un botón de adentro, Enter tiene que clickear ese botón, no abrir la fila.
      const target = ev.target as HTMLElement | null;
      if (!target?.hasAttribute?.("data-roving-item")) return;

      const accion = rovingActionForKey(ev.key, ev.ctrlKey || ev.metaKey || ev.altKey);
      if (!accion) return;
      ev.preventDefault();

      if (accion === "open") {
        if (activeIndex >= 0) opts.onOpen(activeIndex);
        return;
      }
      if (accion === "escape") {
        opts.onEscape?.();
        return;
      }

      const destino = nextRovingIndex(accion, activeIndex, opts.itemCount);
      if (destino < 0) return;
      setActiveIndex(destino);
      // El atributo es estático, así que la fila destino ya está en el DOM aunque
      // el re-render por setActiveIndex todavía no haya corrido.
      const nodo = containerRef.current?.querySelector(
        `[data-roving-item="${destino}"]`,
      ) as HTMLElement | null;
      nodo?.focus();
    },
    [activeIndex, opts],
  );

  const rowProps = useCallback(
    (index: number) => ({
      // Sin fila activa, la primera lleva tabIndex 0 para que Tab entre a la lista.
      tabIndex: index === Math.max(0, clampRovingIndex(activeIndex, opts.itemCount)) ? 0 : -1,
      "data-roving-item": String(index),
      // Un click del mouse sincroniza el roving: mouse y teclado nunca divergen.
      onFocus: () => setActiveIndex(index),
    }),
    [activeIndex, opts.itemCount],
  );

  return { activeIndex, containerProps: { onKeyDown, ref: containerRef }, rowProps };
}

export default useRovingFocus;
