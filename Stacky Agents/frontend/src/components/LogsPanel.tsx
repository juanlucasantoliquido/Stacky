import { useEffect, useRef } from "react";

import { useExecutionStream } from "../hooks/useExecutionStream";
import { useUiPerfFlags } from "../hooks/useUiPerfFlags";
import { useVirtualList } from "../hooks/useVirtualList";
import { useWorkbench } from "../store/workbench";
import { isPinnedToBottom } from "../utils/stickToBottom";
import styles from "./LogsPanel.module.css";

// Plan 156 F3 — cap de render: solo se pinta la cola (el ring ya acota el total
// retenido a 5000; renderizar todo igual sería el cuello de botella de DOM).
const RENDER_CAP = 2000;

// Plan 174 F2 — altura fija de fila, requisito del motor de virtualización.
const LOG_ROW_HEIGHT_PX = 20;

export default function LogsPanel() {
  const { runningExecutionId, activeExecutionId } = useWorkbench();
  const target = runningExecutionId ?? activeExecutionId;
  const stream = useExecutionStream(target);
  const ref = useRef<HTMLDivElement>(null);
  const padTopRef = useRef<HTMLDivElement>(null);
  const padBottomRef = useRef<HTMLDivElement>(null);

  const flags = useUiPerfFlags();
  const virt = useVirtualList({
    total: stream.lines.length,
    rowHeightPx: LOG_ROW_HEIGHT_PX,
    enabled: flags.virtualization,
  });

  // Las alturas de los spacers se setean por ref, no como estilo inline en el
  // JSX: el ratchet del plan 138 lo prohíbe, y acá además cambiarían en cada
  // frame de scroll.
  useEffect(() => {
    if (padTopRef.current) padTopRef.current.style.height = `${virt.padTopPx}px`;
    if (padBottomRef.current) padBottomRef.current.style.height = `${virt.padBottomPx}px`;
  }, [virt.padTopPx, virt.padBottomPx]);

  useEffect(() => {
    const el = virt.isVirtualized ? virt.containerRef.current : ref.current;
    if (!el) return;
    if (!virt.isVirtualized) {
      // Camino sin virtualizar: idéntico a siempre.
      el.scrollTop = el.scrollHeight;
      return;
    }
    // Virtualizado: solo se sigue el fondo si el operador YA estaba ahí. Si se
    // fue a leer algo más arriba, arrastrarlo al fondo le saca lo que está
    // mirando en plena ejecución larga.
    if (isPinnedToBottom(el.scrollTop, el.clientHeight, el.scrollHeight)) {
      virt.scrollToIndex(stream.lines.length - 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream.lines.length, virt.isVirtualized]);

  const visibles = virt.isVirtualized
    ? stream.lines.slice(virt.start, virt.end)
    : stream.lines.slice(-RENDER_CAP);
  const offset = virt.isVirtualized ? virt.start : 0;

  return (
    <section className={styles.section}>
      <header className={styles.head}>
        LOGS {target ? `— exec #${target}` : ""}
        {stream.done ? <span className="muted"> (done)</span> : null}
      </header>
      <div
        className={styles.body}
        role="log"
        ref={virt.isVirtualized ? virt.containerRef : ref}
        onScroll={virt.isVirtualized ? virt.onScroll : undefined}
      >
        {stream.lines.length === 0 && (
          <div className="muted">sin logs</div>
        )}
        {(stream.dropped ?? 0) > 0 && (
          <div className={styles.dropped}>{stream.dropped} líneas anteriores descartadas</div>
        )}
        {virt.isVirtualized && <div ref={padTopRef} />}
        {visibles.map((l, i) => (
          <div
            key={offset + i}
            className={`${styles.line} ${virt.isVirtualized ? styles.virtualLine : ""} ${styles[l.level]}`}
          >
            <span className={styles.ts}>
              {new Date(l.timestamp).toLocaleTimeString()}
            </span>
            <span className={styles.msg}>{l.message}</span>
          </div>
        ))}
        {virt.isVirtualized && <div ref={padBottomRef} />}
      </div>
    </section>
  );
}
