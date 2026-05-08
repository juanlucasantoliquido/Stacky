import type { PipelineInferenceResult } from "../types";
import styles from "./PipelineStatus.module.css";

const STAGE_ORDER = ["business", "functional", "technical", "developer", "qa"];
const STAGE_ICONS: Record<string, string> = {
  business:   "💼",
  functional: "🔍",
  technical:  "🔬",
  developer:  "🚀",
  qa:         "✅",
};
const STAGE_SHORT: Record<string, string> = {
  business:   "Negocio",
  functional: "Funcional",
  technical:  "Técnico",
  developer:  "Dev",
  qa:         "QA",
};

interface Props {
  result: PipelineInferenceResult;
  compact?: boolean;
}

export default function PipelineStatus({ result, compact = false }: Props) {
  const pct = Math.round(result.overall_progress * 100);

  return (
    <div className={`${styles.root} ${compact ? styles.compact : ""}`}>
      {/* Barra de progreso */}
      <div className={styles.progressBar}>
        <div className={styles.progressFill} style={{ width: `${pct}%` }} />
      </div>

      {/* Etapas */}
      <div className={styles.stages}>
        {STAGE_ORDER.map((stage) => {
          const s = result.stages[stage];
          if (!s) return null;
          const isNext = stage === result.next_suggested;
          return (
            <div
              key={stage}
              className={[
                styles.stage,
                s.done ? styles.done : styles.pending,
                isNext ? styles.next : "",
              ].join(" ")}
              title={s.evidence || s.label}
            >
              <span className={styles.stageIcon}>{STAGE_ICONS[stage]}</span>
              {!compact && (
                <span className={styles.stageLabel}>{STAGE_SHORT[stage]}</span>
              )}
              {s.done && (
                <span className={styles.checkmark}>✓</span>
              )}
              {!s.done && isNext && (
                <span className={styles.arrow}>→</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Resumen + metadata */}
      {!compact && result.summary && (
        <p className={styles.summary}>{result.summary}</p>
      )}
      {!compact && (
        <div className={styles.meta}>
          <span>{pct}% completado</span>
          {result.next_suggested && (
            <span className={styles.nextLabel}>
              Próximo: <strong>{STAGE_SHORT[result.next_suggested] ?? result.next_suggested}</strong>
            </span>
          )}
          <span className={styles.source}>
            {result.source === "cache" ? "⚡ cache" : "🤖 LLM"}
            {" · "}
            {result.model_used}
          </span>
        </div>
      )}
    </div>
  );
}
