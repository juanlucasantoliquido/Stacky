import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { formatCostUsd, formatPercent } from "../services/format";
import { publishActivity } from "../services/activityCenter"; // Plan 152 F6b
import { shouldPublishCostTransition } from "../services/runCapture"; // Plan 152 F6b
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
  // Plan 152 F6b — recuerda el estado anterior para publicar SOLO en transición.
  const prevStateRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      const url = projectName
        ? `/api/cost-cap?project=${encodeURIComponent(projectName)}`
        : "/api/cost-cap";
      api
        .get<CostCapResponse>(url)
        .then((d) => {
          if (cancelled) return;
          // Plan 152 F6b — publica un aviso de costo SOLO al cruzar/entre
          // alert|over|blocked. El poll de 60 s repite el mismo estado y NO
          // re-publica (anti-ruido); la key incluye el estado ⇒ dedup en el store.
          if (shouldPublishCostTransition(prevStateRef.current, d.state)) {
            publishActivity({
              key: `cost:${d.project ?? "global"}:${d.state}`,
              kind: "cost",
              severity: "attention",
              title: `Costo mensual en estado ${d.state}`,
              body: `${formatCostUsd(d.spent_usd)} / ${formatCostUsd(d.monthly_cap_usd)} (${formatPercent(d.spent_pct)})`,
              ts: Date.now(),
            });
          }
          prevStateRef.current = d.state;
          setData(d);
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

  const title = `Costo mensual: ${formatCostUsd(data.spent_usd)} / ${formatCostUsd(data.monthly_cap_usd)} (${formatPercent(data.spent_pct)})`;

  return (
    <span className={`${styles.chip} ${stateClass}`} title={title}>
      <span aria-hidden="true">💰</span>
      {formatCostUsd(data.spent_usd)}/{Math.round(data.monthly_cap_usd)}
      <span className={styles.bar} aria-hidden="true">
        <span
          className={styles.fill}
          style={{ width: `${Math.min(100, data.spent_pct)}%` }}
        />
      </span>
    </span>
  );
}
