import { Card } from "../ui";
import type { CostFiltersParams, CostKind } from "../../lib/costCenterTypes";
import styles from "./CostFiltersBar.module.css";

export interface CostFiltersBarProps {
  value: CostFiltersParams;
  onChange: (next: CostFiltersParams) => void;
}

/** Plan 142 F6 — controles de filtro globales (rango de días, runtime, modelo,
 * agente, proyecto, estado, cost_kind); actualizan el estado del padre, que
 * refetchea los 3 endpoints (react-query, CostCenterPage). */
export default function CostFiltersBar({ value, onChange }: CostFiltersBarProps) {
  const setField = <K extends keyof CostFiltersParams>(key: K, next: CostFiltersParams[K]) => {
    onChange({ ...value, [key]: next || undefined });
  };

  return (
    <Card padding="sm">
      <div className={styles.bar}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Días</span>
          <input
            type="number" min={1} max={365}
            value={value.days ?? 30}
            onChange={(e) => setField("days", Number(e.target.value) || undefined)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Runtime</span>
          <input
            type="text" placeholder="claude_code_cli"
            value={value.runtime ?? ""}
            onChange={(e) => setField("runtime", e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Modelo</span>
          <input
            type="text" placeholder="claude-sonnet-5"
            value={value.model ?? ""}
            onChange={(e) => setField("model", e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Agente</span>
          <input
            type="text" placeholder="developer"
            value={value.agent_type ?? ""}
            onChange={(e) => setField("agent_type", e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Proyecto</span>
          <input
            type="text"
            value={value.project ?? ""}
            onChange={(e) => setField("project", e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Estado (csv)</span>
          <input
            type="text" placeholder="completed,error"
            value={value.status ?? ""}
            onChange={(e) => setField("status", e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Tipo de costo</span>
          <select
            value={value.cost_kind ?? ""}
            onChange={(e) => setField("cost_kind", (e.target.value || undefined) as CostKind | undefined)}
          >
            <option value="">Todos</option>
            <option value="reported">Reportado</option>
            <option value="estimated">Estimado</option>
            <option value="nominal">Nominal</option>
            <option value="unknown">n/d</option>
          </select>
        </label>
      </div>
    </Card>
  );
}
