import { useState } from "react";
import { useModelCatalog } from "../hooks/useModelCatalog";
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

// Plan 159 — labels y alternativas de modelo vienen del catálogo único
// (useModelCatalog); ya no se declaran acá (corrige el bug del modelo stale).

export default function ModelDecisionChip({ decision, onRerun }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { catalog } = useModelCatalog();
  const claudeModels = catalog.claude_code_cli?.models ?? [];

  if (!decision || !decision.model) return null;

  const cost = decision.cost_estimate;
  const costStr =
    typeof cost === "number" && Number.isFinite(cost)
      ? ` ($${cost.toFixed(2)})`
      : "";
  const modelLabel =
    claudeModels.find((m) => m.id === decision.model)?.label ?? decision.model;
  const alternatives = claudeModels
    .map((m) => m.id)
    .filter((id) => id !== decision.model);

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
                  {claudeModels.find((mm) => mm.id === m)?.label ?? m}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
