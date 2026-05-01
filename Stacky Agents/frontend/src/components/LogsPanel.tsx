import { useEffect, useRef } from "react";

import { useExecutionStream } from "../hooks/useExecutionStream";
import { useWorkbench } from "../store/workbench";
import styles from "./LogsPanel.module.css";

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
        {stream.lines.map((l, i) => (
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
