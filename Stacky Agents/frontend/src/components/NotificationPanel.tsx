import { useEffect, useRef } from "react";
import EmptyState from "./EmptyState";
import type { ActivityEvent } from "../services/activityReducer";
import styles from "./NotificationPanel.module.css";

interface Props {
  groups: Record<string, ActivityEvent[]>;
  onNavigate?: (nav: { tab: string; executionId?: number }) => void;
  onClose: () => void;
}

/** Orden de secciones; los kinds desconocidos van al final bajo su propio nombre. */
const KIND_ORDER = ["run", "error", "cost"];
const KIND_LABEL: Record<string, string> = {
  run: "Ejecuciones",
  error: "Errores",
  cost: "Costos",
};

/** Hora relativa humana y corta. Pura, sin dependencias. */
function relativeTime(ts: number, now: number): string {
  const diff = Math.max(0, now - ts);
  const s = Math.floor(diff / 1000);
  if (s < 60) return "hace instantes";
  const m = Math.floor(s / 60);
  if (m < 60) return `hace ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `hace ${h} h`;
  const d = Math.floor(h / 24);
  return `hace ${d} d`;
}

function orderedKinds(groups: Record<string, ActivityEvent[]>): string[] {
  const present = Object.keys(groups);
  const known = KIND_ORDER.filter((k) => present.includes(k));
  const unknown = present.filter((k) => !KIND_ORDER.includes(k)).sort();
  return [...known, ...unknown];
}

export default function NotificationPanel({ groups, onNavigate, onClose }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const now = Date.now();
  const kinds = orderedKinds(groups);
  const isEmpty = kinds.length === 0;

  // Cerrar con Escape o click fuera del panel (comportamiento estándar de dropdown).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [onClose]);

  return (
    <div
      className={styles.panel}
      role="dialog"
      aria-label="Centro de actividad"
      ref={ref}
    >
      <div className={styles.header}>
        <h2 className={styles.title}>Actividad</h2>
        <button
          type="button"
          className={styles.close}
          onClick={onClose}
          aria-label="Cerrar"
          title="Cerrar"
        >
          ×
        </button>
      </div>

      {isEmpty ? (
        <div className={styles.empty}>
          <EmptyState variant="history" />
        </div>
      ) : (
        kinds.map((kind) => (
          <section className={styles.section} key={kind}>
            <h3 className={styles.sectionTitle}>{KIND_LABEL[kind] ?? kind}</h3>
            {groups[kind].map((item) => (
              <div className={styles.item} key={item.key} data-severity={item.severity}>
                <span className={styles.dot} aria-hidden="true" />
                <div className={styles.itemMain}>
                  <p className={styles.itemTitle}>{item.title}</p>
                  {item.body && <p className={styles.itemBody}>{item.body}</p>}
                  <div className={styles.itemMeta}>
                    <span className={styles.itemTime}>{relativeTime(item.ts, now)}</span>
                    {item.nav && onNavigate && (
                      <button
                        type="button"
                        className={styles.viewBtn}
                        onClick={() => {
                          onNavigate(item.nav!);
                          onClose();
                        }}
                      >
                        Ver
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </section>
        ))
      )}
    </div>
  );
}
