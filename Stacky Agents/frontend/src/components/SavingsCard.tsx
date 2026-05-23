import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./SavingsCard.module.css";

interface SavingsResponse {
  ok: boolean;
  user: string;
  week_start: string | null;
  tickets_closed_with_agents: number;
  real_time_ms: number;
  baseline_time_ms: number;
  savings_ms: number;
  calibrated: boolean;
  calibration_min_samples: number;
  note: string;
}

function formatMs(ms: number): string {
  if (!ms) return "0m";
  const totalMin = Math.round(ms / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

export default function SavingsCard() {
  const [data, setData] = useState<SavingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<SavingsResponse>("/api/savings/weekly")
      .then(setData)
      .catch((err) => setError(String(err)));
  }, []);

  if (error) return null;
  if (!data) {
    return (
      <div className={`${styles.card} ${styles.loading}`} aria-hidden="true">
        <span>Calculando ahorro semanal…</span>
      </div>
    );
  }

  if (data.tickets_closed_with_agents === 0) {
    return (
      <div className={styles.card}>
        <h3 className={styles.title}>📊 Esta semana</h3>
        <p className={styles.empty}>
          Todavía no cerraste tickets con asistencia de agentes esta semana. Cuando
          lo hagas, acá vas a ver el ahorro estimado.
        </p>
      </div>
    );
  }

  const savings = data.savings_ms;
  const positive = savings > 0;

  return (
    <div className={styles.card}>
      <h3 className={styles.title}>📊 Esta semana</h3>
      <table className={styles.table}>
        <tbody>
          <tr>
            <td>Tickets cerrados con agentes:</td>
            <td className={styles.value}>{data.tickets_closed_with_agents}</td>
          </tr>
          <tr>
            <td>Tiempo real:</td>
            <td className={styles.value}>{formatMs(data.real_time_ms)}</td>
          </tr>
          <tr>
            <td>Baseline (sin agentes):</td>
            <td className={styles.value}>{formatMs(data.baseline_time_ms)}</td>
          </tr>
          <tr className={positive ? styles.savedRow : styles.lossRow}>
            <td>
              <strong>{positive ? "Ahorrado:" : "Tiempo extra:"}</strong>
            </td>
            <td className={styles.value}>
              <strong>{formatMs(Math.abs(savings))}</strong>
            </td>
          </tr>
        </tbody>
      </table>
      <p className={styles.note}>
        {data.calibrated ? "✓ " : "⚠ "}
        {data.note}
      </p>
    </div>
  );
}
