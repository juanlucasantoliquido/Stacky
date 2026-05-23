import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./CostCapIndicator.module.css";

interface CostCapResponse {
  ok: boolean;
  project: string | null;
  monthly_cap_usd: number;
  alert_pct: number;
  block_at_100: boolean;
  spent_usd: number;
  spent_pct: number;
  state: "unset" | "ok" | "alert" | "over" | "blocked";
}

interface Props {
  projectName: string | null;
}

export default function CostCapIndicator({ projectName }: Props) {
  const [data, setData] = useState<CostCapResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      const url = projectName
        ? `/api/cost-cap?project=${encodeURIComponent(projectName)}`
        : "/api/cost-cap";
      api
        .get<CostCapResponse>(url)
        .then((d) => {
          if (!cancelled) setData(d);
        })
        .catch(() => {
          if (!cancelled) setData(null);
        });
    };
    refresh();
    const t = window.setInterval(refresh, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [projectName]);

  if (!data || data.state === "unset") return null;

  const stateClass =
    data.state === "alert" ? styles.alert :
    data.state === "over" || data.state === "blocked" ? styles.over :
    styles.ok;

  const title = `Costo mensual: $${data.spent_usd.toFixed(2)} / $${data.monthly_cap_usd.toFixed(2)} (${data.spent_pct.toFixed(0)}%)`;

  return (
    <span className={`${styles.chip} ${stateClass}`} title={title}>
      <span aria-hidden="true">💰</span>
      ${data.spent_usd.toFixed(2)}/{data.monthly_cap_usd.toFixed(0)}
      <span className={styles.bar} aria-hidden="true">
        <span
          className={styles.fill}
          style={{ width: `${Math.min(100, data.spent_pct)}%` }}
        />
      </span>
    </span>
  );
}
