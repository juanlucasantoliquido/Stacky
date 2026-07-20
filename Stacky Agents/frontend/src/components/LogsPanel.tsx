import { useEffect, useRef } from "react";

import { useExecutionStream } from "../hooks/useExecutionStream";
import { useWorkbench } from "../store/workbench";
import styles from "./LogsPanel.module.css";

// Plan 156 F3 — cap de render: solo se pinta la cola (el ring ya acota el total
// retenido a 5000; renderizar todo igual sería el cuello de botella de DOM).
const RENDER_CAP = 2000;

export default function LogsPanel() {
  const { runningExecutionId, activeExecutionId } = useWorkbench();
  const target = runningExecutionId ?? activeExecutionId;
  const stream = useExecutionStream(target);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [stream.lines.length]);

  return (
    <section className={styles.section}>
      <header className={styles.head}>
        LOGS {target ? `— exec #${target}` : ""}
        {stream.done ? <span className="muted"> (done)</span> : null}
      </header>
      <div className={styles.body} ref={ref}>
        {stream.lines.length === 0 && (
          <div className="muted">sin logs</div>
        )}
        {(stream.dropped ?? 0) > 0 && (
          <div className={styles.dropped}>{stream.dropped} líneas anteriores descartadas</div>
        )}
        {stream.lines.slice(-RENDER_CAP).map((l, i) => (
          <div key={i} className={`${styles.line} ${styles[l.level]}`}>
            <span className={styles.ts}>
              {new Date(l.timestamp).toLocaleTimeString()}
            </span>
            <span className={styles.msg}>{l.message}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
