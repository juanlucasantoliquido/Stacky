import { Card, Input, Select } from "../ui";
import type { CostFiltersParams, CostKind, CostSource } from "../../lib/costCenterTypes";
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

  /* Plan 199 F4 — los umbrales de costo aceptan 0 como valor legítimo, así que
   * NO se puede usar `setField` (su `next || undefined` colapsaría el 0 a "sin
   * filtro"). Un input vacío sí borra el filtro. */
  const setCostBound = (key: "min_cost" | "max_cost", raw: string) => {
    const limpio = raw.trim();
    if (limpio === "") {
      onChange({ ...value, [key]: undefined });
      return;
    }
    const num = Number(limpio);
    onChange({ ...value, [key]: Number.isFinite(num) ? num : undefined });
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
        {/* Plan 199 F4 — multi-valor (OR) y rango de costo. Conviven con los
            singulares de arriba: el backend aplica ambos. */}
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Runtimes (csv)</span>
          <Input
            type="text" placeholder="codex_cli,claude_code_cli"
            value={value.runtimes ?? ""}
            onChange={(e) => setField("runtimes", e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Modelos (csv)</span>
          <Input
            type="text" placeholder="gpt-5,claude-opus-5"
            value={value.models ?? ""}
            onChange={(e) => setField("models", e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Costo min (USD)</span>
          <Input
            type="number" min={0} step="0.01" placeholder="0.00"
            value={value.min_cost ?? ""}
            onChange={(e) => setCostBound("min_cost", e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Costo max (USD)</span>
          <Input
            type="number" min={0} step="0.01" placeholder="sin tope"
            value={value.max_cost ?? ""}
            onChange={(e) => setCostBound("max_cost", e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Fuente</span>
          <Select
            value={value.source ?? "live"}
            onChange={(e) => setField("source", e.target.value as CostSource)}
          >
            <option value="live">En vivo</option>
            <option value="harvest">Cosecha histórica</option>
            <option value="all">Ambas</option>
          </Select>
        </label>
      </div>
    </Card>
  );
}
