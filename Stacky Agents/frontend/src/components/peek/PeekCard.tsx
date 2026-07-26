import { useLayoutEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { clampMenuPosition } from "../../services/contextMenuModel";
import type { PeekContent, PeekState } from "../../services/peekModel";
import styles from "./PeekCard.module.css";

/**
 * Plan 175 F2 — Lo esencial de una entidad sin abrir su detalle.
 *
 * La tarjeta NUNCA toma el foco: aparece por hover, y robarle el foco al
 * operador que está tipeando o recorriendo la lista con el teclado sería peor
 * que no mostrar nada.
 */
export function PeekCard({
  state,
  content,
  anchorRect,
  loading,
  onCardHover,
  onCardLeave,
}: {
  state: PeekState;
  content: PeekContent | null;
  anchorRect: DOMRect | null;
  loading?: boolean;
  onCardHover: () => void;
  onCardLeave: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const visible = state.phase === "open" || state.phase === "closing";

  // La posición se asigna imperativamente: el ratchet del plan 138 no admite
  // estilos inline en el JSX, y acá cambia con cada fila.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !anchorRect) return;
    const caja = el.getBoundingClientRect();
    const p = clampMenuPosition(
      anchorRect.left,
      anchorRect.bottom + 6,
      caja.width,
      caja.height,
      window.innerWidth,
      window.innerHeight,
    );
    el.style.left = `${p.left}px`;
    el.style.top = `${p.top}px`;
  }, [anchorRect, content, visible]);

  if (!visible) return null;

  return createPortal(
    <div
      ref={ref}
      className={styles.card}
      role="tooltip"
      onMouseEnter={onCardHover}
      onMouseLeave={onCardLeave}
    >
      {loading && <div className={styles.title}>Cargando…</div>}
      {!loading && content && (
        <>
          <div className={styles.title}>{content.title}</div>
          {content.fields.map((f) => (
            <div key={f.label} className={styles.row}>
              <span className={styles.label}>{f.label}</span>
              <span className={`${styles.value} ${f.mono ? styles.mono : ""}`}>{f.value}</span>
            </div>
          ))}
        </>
      )}
    </div>,
    document.body,
  );
}

export default PeekCard;
