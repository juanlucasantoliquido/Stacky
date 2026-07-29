/**
 * DocGraphZoomControls.tsx — Plan 268 F3.
 *
 * Hace descubrible el zoom que en el plan 111 solo existía en la rueda del mouse.
 * Cascarón puro de presentación: no calcula nada, no toca el viewport; solo avisa
 * el click. Cero atributos de estilo en línea (G8): todo por clases del módulo CSS.
 */
import styles from "./DocGraphExplorer.module.css";

interface DocGraphZoomControlsProps {
  scale: number; // solo para el % que se muestra
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onReset: () => void;
  canZoomIn: boolean; // scale < MAX_SCALE
  canZoomOut: boolean; // scale > MIN_SCALE
}

export default function DocGraphZoomControls({
  scale,
  onZoomIn,
  onZoomOut,
  onFit,
  onReset,
  canZoomIn,
  canZoomOut,
}: DocGraphZoomControlsProps) {
  return (
    <div className={styles.zoomControls}>
      <button
        type="button"
        className={styles.zoomBtn}
        onClick={onZoomOut}
        disabled={!canZoomOut}
        title="Alejar (tecla −)"
        aria-label="Alejar"
      >
        &#8722;
      </button>
      <span className={styles.zoomPct}>{Math.round(scale * 100)}%</span>
      <button
        type="button"
        className={styles.zoomBtn}
        onClick={onZoomIn}
        disabled={!canZoomIn}
        title="Acercar (tecla +)"
        aria-label="Acercar"
      >
        +
      </button>
      <button
        type="button"
        className={styles.zoomBtn}
        onClick={onFit}
        title="Ajustar a pantalla (tecla F)"
        aria-label="Ajustar a pantalla"
      >
        &#9974;
      </button>
      <button
        type="button"
        className={styles.zoomBtn}
        onClick={onReset}
        title="Restablecer vista (tecla 0)"
        aria-label="Restablecer vista"
      >
        &#8634;
      </button>
    </div>
  );
}
