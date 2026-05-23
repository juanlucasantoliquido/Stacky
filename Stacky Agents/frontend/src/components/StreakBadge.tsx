import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./StreakBadge.module.css";

interface StreakResponse {
  ok: boolean;
  user: string;
  current_streak: number;
  best_streak: number;
  last_close_at: string | null;
}

export default function StreakBadge() {
  const [data, setData] = useState<StreakResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      api
        .get<StreakResponse>("/api/streak")
        .then((d) => {
          if (!cancelled) setData(d);
        })
        .catch(() => {
          if (!cancelled) setData(null);
        });
    };
    refresh();
    const t = window.setInterval(refresh, 5 * 60 * 1000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  if (!data || data.current_streak <= 0) return null;

  const title = `${data.current_streak} días seguidos cerrando tickets con asistencia de agentes.\nMejor racha: ${data.best_streak}.`;

  return (
    <span className={styles.badge} title={title} aria-label={title}>
      <span aria-hidden="true">🔥</span>
      <span className={styles.count}>{data.current_streak}</span>
    </span>
  );
}
