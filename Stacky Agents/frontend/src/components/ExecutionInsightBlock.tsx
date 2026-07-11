/**
 * ExecutionInsightBlock.tsx — Plan 117 F4.
 *
 * Bloque presentacional + acción para el insight local de una ejecución (drawer).
 * Sin insight → botón "Generar"; done → TL;DR + labels + riesgo + triage; failed →
 * error + Reintentar. La generación es HITL (click del operador).
 */
import { useState } from "react";
import { LocalLlmApi } from "../api/endpoints";
import type { ExecutionLocalInsight } from "../api/endpoints";
import styles from "./ExecutionInsightBlock.module.css";

interface Props {
  executionId: number;
  insight: ExecutionLocalInsight | null | undefined;
  onRegenerated?: () => void;
}

const RISK_CLASS: Record<string, string> = {
  low: styles.riskLow,
  medium: styles.riskMedium,
  high: styles.riskHigh,
};

export default function ExecutionInsightBlock({ executionId, insight, onRegenerated }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      await LocalLlmApi.generateInsight(executionId);
      onRegenerated?.();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes("local_insights_disabled")
          ? 'Activá "Insights locales de ejecuciones" en Configuración → Arnés'
          : msg,
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className={styles.block}>
      <h4 className={styles.title}>Insight (IA local)</h4>

      {insight?.state === "done" && (
        <>
          <p className={styles.tldr}>{insight.tldr}</p>
          {insight.labels && insight.labels.length > 0 && (
            <div className={styles.labels}>
              {insight.labels.map((l, i) => (
                <span key={i} className={styles.label}>{l}</span>
              ))}
            </div>
          )}
          {insight.risk && (
            <span className={`${styles.riskBadge} ${RISK_CLASS[insight.risk] ?? styles.riskLow}`}>
              riesgo: {insight.risk}
            </span>
          )}
          {(insight.probable_cause || insight.evidence || insight.next_step) && (
            <div className={styles.triage}>
              {insight.probable_cause && <div><b>Causa probable:</b> {insight.probable_cause}</div>}
              {insight.evidence && <div><b>Evidencia:</b> {insight.evidence}</div>}
              {insight.next_step && <div><b>Siguiente paso sugerido:</b> {insight.next_step}</div>}
            </div>
          )}
          <div className={styles.foot}>
            {insight.generated_at} · {insight.model}
          </div>
        </>
      )}

      {insight?.state === "failed" && (
        <div className={styles.failed}>
          <p>No se pudo generar el insight{insight.error ? `: ${insight.error}` : ""}</p>
          <button type="button" disabled={loading} onClick={generate}>
            {loading ? "Generando…" : "Reintentar"}
          </button>
        </div>
      )}

      {!insight && (
        <button type="button" disabled={loading} onClick={generate}>
          {loading ? "Generando…" : "Generar insight (IA local)"}
        </button>
      )}

      {error && <p className={styles.error}>{error}</p>}
    </section>
  );
}
