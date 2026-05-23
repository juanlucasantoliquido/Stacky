import { useState } from "react";
import styles from "./ModelDecisionChip.module.css";

interface RoutingDecision {
  model?: string;
  reason?: string;
  cost_estimate?: number | null;
}

interface Props {
  decision?: RoutingDecision | null;
  onRerun?: (model: string) => void;
}

const ALT_MODELS = ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"];

const MODEL_LABEL: Record<string, string> = {
  "claude-opus-4-7": "Opus",
  "claude-sonnet-4-6": "Sonnet",
  "claude-haiku-4-5": "Haiku",
};

export default function ModelDecisionChip({ decision, onRerun }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!decision || !decision.model) return null;

  const cost = decision.cost_estimate;
  const costStr =
    typeof cost === "number" && Number.isFinite(cost)
      ? ` ($${cost.toFixed(2)})`
      : "";
  const modelLabel = MODEL_LABEL[decision.model] ?? decision.model;
  const alternatives = ALT_MODELS.filter((m) => m !== decision.model);

  return (
    <div className={styles.wrap}>
      <button
        className={styles.chip}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        title={decision.reason ?? "Decisión de routing"}
      >
        <span aria-hidden="true">ⓘ</span>
        Modelo: {modelLabel}{costStr}
      </button>
      {expanded && (
        <div className={styles.detail}>
          <p className={styles.reason}>
            <strong>Por qué:</strong> {decision.reason ?? "(no informado)"}
          </p>
          {onRerun && (
            <div className={styles.rerunRow}>
              <span className={styles.rerunLabel}>Re-correr con:</span>
              {alternatives.map((m) => (
                <button
                  key={m}
                  className={styles.rerunBtn}
                  onClick={() => onRerun(m)}
                >
                  {MODEL_LABEL[m] ?? m}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
