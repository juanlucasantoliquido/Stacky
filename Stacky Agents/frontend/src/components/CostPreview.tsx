/*
 * FA-33 — Cost preview pre-Run.
 * Muestra estimación de tokens, costo USD y latencia para el contexto actual.
 * Si hay cache hit (FA-31), badge "🔁 cached — gratis".
 * Debounced para no saturar al backend mientras el operador edita.
 */
import { useEffect, useState } from "react";

import { Agents } from "../api/endpoints";
import type { AgentType, ContextBlock } from "../types";
import styles from "./CostPreview.module.css";

interface Props {
  agentType: AgentType | null;
  blocks: ContextBlock[];
}

interface Estimate {
  tokens_in: number;
  tokens_out: number;
  cost_usd_total: number;
  latency_ms: number;
  cache_hit: boolean;
  model: string;
}

export default function CostPreview({ agentType, blocks }: Props) {
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!agentType || blocks.length === 0) {
      setEstimate(null);
      return;
    }
    let cancelled = false;
    const handle = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await Agents.estimate({ agent_type: agentType, context_blocks: blocks });
        if (!cancelled) setEstimate(r);
      } catch {
        if (!cancelled) setEstimate(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [agentType, blocks]);

  if (!agentType) return null;
  if (loading && !estimate) {
    return <div className={styles.box}><span className="muted">estimando…</span></div>;
  }
  if (!estimate) return null;

  if (estimate.cache_hit) {
    return (
      <div className={`${styles.box} ${styles.cached}`}>
        <span title="Output servido desde cache; sin nueva llamada al LLM">
          🔁 cached — gratis · &lt;100ms
        </span>
      </div>
    );
  }

  const costStr = estimate.cost_usd_total < 0.01
    ? `<$0.01`
    : `$${estimate.cost_usd_total.toFixed(2)}`;
  const latencyStr = estimate.latency_ms < 1000
    ? `${estimate.latency_ms}ms`
    : `${(estimate.latency_ms / 1000).toFixed(1)}s`;

  return (
    <div className={styles.box} title={`Modelo: ${estimate.model}`}>
      <span className={styles.tokens}>
        {(estimate.tokens_in / 1000).toFixed(1)}k → {(estimate.tokens_out / 1000).toFixed(1)}k tok
      </span>
      <span className={styles.dot}>·</span>
      <span className={styles.cost}>{costStr}</span>
      <span className={styles.dot}>·</span>
      <span className={styles.latency}>~{latencyStr}</span>
    </div>
  );
}
