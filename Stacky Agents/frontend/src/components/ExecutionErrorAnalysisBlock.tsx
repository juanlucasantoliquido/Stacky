/**
 * ExecutionErrorAnalysisBlock.tsx — Plan 127 F6 (C1).
 *
 * Bloque presentacional + acción para el análisis de error de una ejecución
 * fallida (drawer), hermano de ExecutionInsightBlock.tsx. Sin análisis →
 * botón "Analizar error con IA local"; con análisis → markdown persistido +
 * caption modelo/latencia + botón "Regenerar". HITL: la generación es SIEMPRE
 * por click del operador.
 */
import { useState } from "react";
import { LocalLlmApi } from "../api/endpoints";
import { shouldOfferErrorAnalysis, disabledHint } from "../executions/errorAnalysisModel";
import styles from "./ExecutionErrorAnalysisBlock.module.css";

interface ErrorAnalysis {
  analysis: string;
  model?: string;
  generated_at?: string;
  analyzer_execution_id?: number;
  elapsed_ms?: number;
}

interface Props {
  executionId: number;
  status: string;
  metadata: Record<string, unknown> | null;
  onRegenerated?: () => void;
}

function extractHttpStatus(e: unknown): number {
  if (e instanceof Error) {
    const match = e.message.match(/^(\d{3})\s/);
    if (match) return Number(match[1]);
  }
  return 0;
}

export default function ExecutionErrorAnalysisBlock({ executionId, status, metadata, onRegenerated }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!shouldOfferErrorAnalysis(status, metadata)) {
    return null;
  }

  const existing = (metadata?.error_analysis ?? null) as ErrorAnalysis | null;

  const analyze = async () => {
    setLoading(true);
    setError(null);
    try {
      await LocalLlmApi.errorAnalysis(executionId);
      onRegenerated?.();
    } catch (e) {
      setError(disabledHint(extractHttpStatus(e)));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className={styles.block}>
      <h4 className={styles.title}>Análisis de error (IA local)</h4>

      {existing?.analysis && (
        <>
          <pre className={styles.analysis}>{existing.analysis}</pre>
          {(existing.model || typeof existing.elapsed_ms === "number") && (
            <div className={styles.foot}>
              {existing.model}
              {existing.model && typeof existing.elapsed_ms === "number" ? " · " : ""}
              {typeof existing.elapsed_ms === "number" ? `${(existing.elapsed_ms / 1000).toFixed(1)}s` : ""}
            </div>
          )}
          <button type="button" disabled={loading} onClick={() => void analyze()}>
            {loading ? "El modelo local puede tardar 1-3 minutos…" : "Regenerar"}
          </button>
        </>
      )}

      {!existing?.analysis && (
        <button type="button" disabled={loading} onClick={() => void analyze()}>
          {loading ? "El modelo local puede tardar 1-3 minutos…" : "Analizar error con IA local"}
        </button>
      )}

      {error && <p className={styles.error}>{error}</p>}
    </section>
  );
}
