import type { CSSProperties } from "react";
import type { CostKind } from "../../lib/costCenterTypes";
import { costKindLabel, costKindTokenVar } from "../../lib/costCenter.logic";
import styles from "./CostBadge.module.css";

export interface CostBadgeProps {
  kind: CostKind;
}

const TITLE_BY_KIND: Partial<Record<CostKind, string>> = {
  nominal: "Nominal: costo de suscripción plana, NUNCA facturable.",
  unknown: "Sin costo ni tokens registrados para este run.",
  estimated: "Estimado a partir de tokens x precio (el CLI no reportó USD real).",
};

/** Plan 142 F6 — badge reported|estimated|nominal|unknown. Color vía
 * costKindTokenVar (F5): siempre var(--status-*), nunca hex (gate Plan 141). */
export default function CostBadge({ kind }: CostBadgeProps) {
  const dotStyle: CSSProperties = { background: costKindTokenVar(kind) };
  return (
    <span className={styles.badge} title={TITLE_BY_KIND[kind]}>
      <span className={styles.dot} style={dotStyle} aria-hidden="true" />
      {costKindLabel(kind)}
    </span>
  );
}
