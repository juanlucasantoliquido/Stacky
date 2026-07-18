// Plan 178 F7 — Panel de avisos de drift (fallback primario, dentro de la página DB Compare).
import { useCallback, useEffect, useState } from "react";

import { DbCompareWatch } from "../../api/endpoints";
import { relativeFromIso } from "./radarLogic";
import type { DriftEvent, DriftEventKind } from "./radarTypes";
import styles from "./dbcompare.module.css";

const KIND_ICON: Record<DriftEventKind, string> = {
  drift_new: "⚠",
  drift_worse: "🔺",
  drift_cleared: "✅",
  baseline_violation: "📌",
  watch_error: "⛔",
};

interface Props {
  refreshKey: number;
  onOpenRun: (runId: string) => void;
  onChanged: () => void;
}

export function DriftEventsPanel({ refreshKey, onOpenRun, onChanged }: Props) {
  const [events, setEvents] = useState<DriftEvent[]>([]);
  const nowMs = Date.now();

  const load = useCallback(() => {
    DbCompareWatch.listEvents(50)
      .then((r) => setEvents(r.events))
      .catch(() => setEvents([]));
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const markAllRead = () => {
    DbCompareWatch.markEventsRead({ all: true })
      .then(() => {
        load();
        onChanged();
      })
      .catch(() => undefined);
  };

  if (events.length === 0) {
    return <div className={styles.radarHint}>Sin avisos de drift todavía.</div>;
  }

  return (
    <div className={styles.eventsPanel}>
      <div className={styles.radarActions}>
        <button type="button" onClick={markAllRead}>
          Marcar todo leído
        </button>
      </div>
      {events.map((e) => {
        const pair = e.source_alias && e.target_alias ? `${e.source_alias} → ${e.target_alias}` : (e.watch_id || "—");
        const rowClass = e.read ? styles.eventRow : `${styles.eventRow} ${styles.eventRowUnread}`;
        return (
          <div
            key={e.event_id}
            className={rowClass}
            onClick={() => {
              if (e.run_id) onOpenRun(e.run_id);
            }}
          >
            <span className={styles.eventKind}>{KIND_ICON[e.kind]}</span>
            <span>{e.kind}</span>
            <span>{pair}</span>
            <span className={styles.eventWhen}>{relativeFromIso(e.created_at, nowMs)}</span>
          </div>
        );
      })}
    </div>
  );
}
