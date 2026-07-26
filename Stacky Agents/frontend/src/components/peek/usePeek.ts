import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import {
  PEEK_CLOSE_DELAY_MS,
  PEEK_IDLE,
  PEEK_OPEN_DELAY_MS,
  peekReducer,
  type PeekTarget,
} from "../../services/peekModel";

/**
 * Plan 175 F2 — Los tiempos del hover sostenido.
 *
 * El reducer decide QUÉ pasa; esto solo maneja los dos temporizadores y el
 * rectángulo de la fila que ancla la tarjeta.
 */
export function usePeek(enabled: boolean) {
  const [state, dispatch] = useReducer(peekReducer, PEEK_IDLE);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
  const abrirRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cerrarRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const limpiar = () => {
    if (abrirRef.current) clearTimeout(abrirRef.current);
    if (cerrarRef.current) clearTimeout(cerrarRef.current);
    abrirRef.current = null;
    cerrarRef.current = null;
  };

  // Un timer vivo después de desmontar abriría una tarjeta sobre una pantalla
  // que ya no existe.
  useEffect(() => () => limpiar(), []);

  useEffect(() => {
    if (!enabled) return;
    const alEscape = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") dispatch({ type: "escape" });
    };
    window.addEventListener("keydown", alEscape);
    return () => window.removeEventListener("keydown", alEscape);
  }, [enabled]);

  const hoverStart = useCallback(
    (target: PeekTarget, rect: DOMRect) => {
      if (!enabled) return;
      limpiar();
      setAnchorRect(rect);
      dispatch({ type: "hover-start", target });
      abrirRef.current = setTimeout(() => dispatch({ type: "open-timer" }), PEEK_OPEN_DELAY_MS);
    },
    [enabled],
  );

  const hoverEnd = useCallback(() => {
    if (!enabled) return;
    if (abrirRef.current) clearTimeout(abrirRef.current);
    dispatch({ type: "hover-end" });
    cerrarRef.current = setTimeout(() => dispatch({ type: "close-timer" }), PEEK_CLOSE_DELAY_MS);
  }, [enabled]);

  const cardHover = useCallback(() => {
    if (cerrarRef.current) clearTimeout(cerrarRef.current);
    dispatch({ type: "card-hover" });
  }, []);

  return { state, anchorRect, hoverStart, hoverEnd, cardHover, cardLeave: hoverEnd };
}

export default usePeek;
