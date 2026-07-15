import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import LoadErrorState from "./LoadErrorState";
import { formatLoadErrorMessage } from "../utils/loadError";
import styles from "./ReplayPlayer.module.css";

interface Event {
  kind: string;
  timestamp: string;
  t_relative_ms?: number;
  payload?: any;
}

interface EventsResponse {
  ok: boolean;
  execution_id: number;
  count: number;
  events: Event[];
}

interface Props {
  executionId: number | null;
  open: boolean;
  onClose: () => void;
}

const SPEEDS = [0.5, 1, 2, 4];

export default function ReplayPlayer({ executionId, open, onClose }: Props) {
  const [events, setEvents] = useState<Event[]>([]);
  const [cursorMs, setCursorMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number | null>(null);

  useEffect(() => {
    if (!open || executionId == null) return;
    setCursorMs(0);
    setPlaying(false);
    setLoadError(null);
    api
      .get<EventsResponse>(`/api/executions/${executionId}/events`)
      .then((d) => setEvents(d.events))
      .catch((err) => { setEvents([]); setLoadError(formatLoadErrorMessage(err)); });
  }, [open, executionId, reloadKey]);

  const totalMs = events.length > 0
    ? (events[events.length - 1].t_relative_ms ?? 0)
    : 0;

  useEffect(() => {
    if (!playing) {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      lastTickRef.current = null;
      return;
    }
    const tick = (now: number) => {
      if (lastTickRef.current === null) lastTickRef.current = now;
      const dt = now - lastTickRef.current;
      lastTickRef.current = now;
      setCursorMs((c) => {
        const next = c + dt * speed;
        if (next >= totalMs) {
          setPlaying(false);
          return totalMs;
        }
        return next;
      });
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, speed, totalMs]);

  if (!open) return null;

  const shown = events.filter((e) => (e.t_relative_ms ?? 0) <= cursorMs);
  const progress = totalMs > 0 ? Math.min(100, (cursorMs / totalMs) * 100) : 0;

  return (
    <div className={styles.backdrop} onClick={(e) => {
      if (e.target === e.currentTarget) onClose();
    }}>
      <div className={styles.modal}>
        <header className={styles.header}>
          <h3>▶ Replay — Execution #{executionId}</h3>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Cerrar">×</button>
        </header>
        <div className={styles.controls}>
          <button
            className={styles.btn}
            onClick={() => setPlaying((p) => !p)}
            disabled={events.length === 0}
          >
            {playing ? "⏸" : "▶"}
          </button>
          <button
            className={styles.btn}
            onClick={() => {
              setCursorMs(0);
              setPlaying(false);
            }}
          >
            ⏮
          </button>
          {SPEEDS.map((s) => (
            <button
              key={s}
              className={`${styles.btn} ${speed === s ? styles.active : ""}`}
              onClick={() => setSpeed(s)}
            >
              {s}×
            </button>
          ))}
          <span className={styles.time}>
            {(cursorMs / 1000).toFixed(1)}s / {(totalMs / 1000).toFixed(1)}s
          </span>
        </div>
        <div className={styles.progressBar}>
          <div className={styles.progressFill} style={{ width: `${progress}%` }} />
        </div>
        <ul className={styles.log}>
          {loadError ? (
            <li className={styles.empty}>
              <LoadErrorState
                compact
                what="los eventos de la grabación"
                error={loadError}
                onRetry={() => setReloadKey((k) => k + 1)}
              />
            </li>
          ) : events.length === 0 ? (
            <li className={styles.empty}>
              Esta ejecución no tiene timeline de eventos registrado.
            </li>
          ) : (
            shown.map((ev, idx) => (
              <li key={idx} className={styles.event}>
                <span className={styles.eventTime}>
                  [{((ev.t_relative_ms ?? 0) / 1000).toFixed(2)}s]
                </span>
                <span className={styles.eventKind}>{ev.kind}</span>
                {ev.payload && Object.keys(ev.payload).length > 0 && (
                  <span className={styles.eventPayload}>
                    {JSON.stringify(ev.payload).slice(0, 140)}
                  </span>
                )}
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
