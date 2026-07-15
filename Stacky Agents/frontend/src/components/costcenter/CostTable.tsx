import { useMemo, useState } from "react";
import { Card, Skeleton } from "../ui";
import EmptyState from "../EmptyState";
import LoadErrorState from "../LoadErrorState";
import CostBadge from "./CostBadge";
import type { CostKind, TopRun } from "../../lib/costCenterTypes";
import { filterRows, formatUsd, sortRows, toCsv } from "../../lib/costCenter.logic";
import type { TableFilterState } from "../../lib/costCenter.logic";
import styles from "./CostTable.module.css";

export interface CostTableProps {
  rows: TopRun[];
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
}

/** Export CSV 100% client-side (Blob de `toCsv`, F5): sin request al backend,
 * sin dependencia nueva (R5/reuso). */
function downloadCsv(rows: TopRun[]): void {
  const csv = toCsv(rows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "stacky-cost-center-runs.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

type SortKey = keyof TopRun;

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "started_at", label: "Cuándo" },
  { key: "ticket_id", label: "Ticket" },
  { key: "agent_type", label: "Agente" },
  { key: "runtime", label: "Runtime" },
  { key: "model", label: "Modelo" },
  { key: "cost_usd", label: "Costo" },
  { key: "cost_kind", label: "Tipo" },
];

/** Plan 142 F6 — tabla de top_runs ordenable (sortRows F5) y filtrable
 * (filterRows F5) por runtime/modelo/agente/ticket/cost_kind, con export CSV
 * client-side (toCsv F5, sin dependencia nueva). */
export default function CostTable({ rows, isLoading, error, onRetry }: CostTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("cost_usd");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [filters, setFilters] = useState<TableFilterState>({});

  const visible = useMemo(
    () => sortRows(filterRows(rows, filters), sortKey, sortDir),
    [rows, filters, sortKey, sortDir],
  );

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  if (error) return <LoadErrorState what="los runs de costo" error={error} onRetry={onRetry} />;

  return (
    <Card padding="sm">
      <div className={styles.toolbar}>
        <input
          className={styles.filterInput}
          placeholder="Filtrar por runtime…"
          value={filters.runtime ?? ""}
          onChange={(e) => setFilters((f) => ({ ...f, runtime: e.target.value || undefined }))}
        />
        <select
          className={styles.filterSelect}
          value={filters.cost_kind ?? ""}
          onChange={(e) =>
            setFilters((f) => ({ ...f, cost_kind: (e.target.value || undefined) as CostKind | undefined }))
          }
        >
          <option value="">Todos los tipos</option>
          <option value="reported">Reportado</option>
          <option value="estimated">Estimado</option>
          <option value="nominal">Nominal</option>
          <option value="unknown">n/d</option>
        </select>
        <button type="button" className={styles.exportBtn} onClick={() => downloadCsv(visible)}>
          Exportar CSV
        </button>
      </div>

      {isLoading ? (
        <Skeleton lines={6} height={22} />
      ) : visible.length === 0 ? (
        <EmptyState
          variant="generic"
          title="Sin runs para mostrar"
          message="Ajustá el rango de fechas o los filtros para ver ejecuciones con costo."
        />
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} className={styles.th} onClick={() => toggleSort(c.key)}>
                  {c.label}
                  {sortKey === c.key ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={r.execution_id}>
                <td>{r.started_at ?? "n/d"}</td>
                <td>{r.ticket_id ?? "n/d"}</td>
                <td>{r.agent_type ?? "n/d"}</td>
                <td>{r.runtime ?? "n/d"}</td>
                <td>{r.model ?? "n/d"}</td>
                <td>{formatUsd(r.cost_usd)}</td>
                <td><CostBadge kind={r.cost_kind} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
