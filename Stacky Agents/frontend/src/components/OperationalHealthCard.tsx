/**
 * OperationalHealthCard.tsx — Plan 46 F3: Panel de Salud Operativa (triage).
 *
 * Consume GET /api/diag/operational-health y muestra triage pasivo solo-lectura
 * de runs recientes en 4 buckets: needs_review, failed, expensive, zombie.
 *
 * Si el flag STACKY_OPERATIONAL_HEALTH_ENABLED está OFF → endpoint devuelve 404 → la card retorna null.
 * Si todos los counts del summary son 0 → mostrar "Todo en orden".
 *
 * Patrón: useEffect + api.get (igual que HarnessHealthCard.tsx).
 */
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { OperationalHealth, type OperationalHealthReport, type OperationalHealthRow } from "../api/endpoints";
import styles from "./OperationalHealthCard.module.css";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt(value: unknown, nullFallback = "—"): string {
  if (value == null) return nullFallback;
  if (typeof value === "number") return String(value);
  return String(value);
}

function fmtCost(value: number | null | undefined): string {
  if (value == null) return "—";
  return `$${value.toFixed(4)}`;
}

// ── Sub-componentes ──────────────────────────────────────────────────────────

interface TableRowProps {
  row: OperationalHealthRow;
  onOpenExecution: (id: number) => void;
  sectionType: "needs_review" | "failed" | "expensive" | "zombie";
}

function TableRow({ row, onOpenExecution, sectionType }: TableRowProps) {
  return (
    <tr>
      <td className={styles.idCell}>
        <span
          className={styles.linkableId}
          onClick={() => onOpenExecution(row.id)}
          title={`Abrir ejecución #${row.id}`}
        >
          #{row.id}
        </span>
      </td>
      <td>{fmt(row.ticket_id)}</td>
      <td>{fmt(row.agent_type)}</td>
      <td>{fmt(row.runtime)}</td>
      <td>{fmt(row.project)}</td>
      <td className={styles.badgeCell}>
        {sectionType === "needs_review" && row.age_days && (
          <span className={styles.badge}>{row.age_days}d</span>
        )}
        {sectionType === "failed" && row.failure_kind && (
          <span className={styles.badge}>{row.failure_kind}</span>
        )}
        {sectionType === "expensive" && row.cost_usd && (
          <span className={styles.badge}>{fmtCost(row.cost_usd)}</span>
        )}
        {sectionType === "expensive" && row.model && (
          <span className={styles.badge}>{row.model}</span>
        )}
        {sectionType === "zombie" && row.age_minutes && (
          <span className={`${styles.badge} ${styles.badgeZombie}`}>{row.age_minutes}m</span>
        )}
        {row.stale && (
          <span className={`${styles.badge} ${styles.badgeStale}`}>envejecida</span>
        )}
      </td>
    </tr>
  );
}

interface SectionProps {
  label: string;
  count: number;
  rows: OperationalHealthRow[];
  onOpenExecution: (id: number) => void;
  sectionType: "needs_review" | "failed" | "expensive" | "zombie";
}

function Section({ label, count, rows, onOpenExecution, sectionType }: SectionProps) {
  if (rows.length === 0) return null;

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>
        {label}
        <span className={styles.sectionCount}>({count})</span>
      </h3>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Ejecución</th>
            <th>Ticket</th>
            <th>Agente</th>
            <th>Runtime</th>
            <th>Proyecto</th>
            <th>Detalles</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <TableRow
              key={row.id}
              row={row}
              onOpenExecution={onOpenExecution}
              sectionType={sectionType}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Componente principal ─────────────────────────────────────────────────────

interface Props {
  /**
   * Callback para abrir el drawer de detalle de una ejecución.
   * La página padre (DiagnosticsPage) lo proporciona.
   */
  onOpenExecution?: (id: number) => void;
}

export default function OperationalHealthCard({ onOpenExecution }: Props) {
  const [data, setData] = useState<OperationalHealthReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    OperationalHealth.get()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) {
          // 404 → flag OFF → no mostrar la card
          if (err?.response?.status === 404) {
            setHidden(true);
          } else {
            setError("No se pudo cargar el reporte de salud operativa.");
          }
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (hidden) return null;

  if (loading) {
    return (
      <div className={styles.card}>
        <p className={styles.loading}>Cargando panel de salud operativa...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={`${styles.card} ${styles.cardError}`}>
        <p className={styles.errorMsg}>{error ?? "Sin datos."}</p>
      </div>
    );
  }

  // Si todos los counts son 0 → "Todo en orden"
  const summary = data.summary;
  const totalIssues =
    summary.needs_review_pending +
    summary.needs_review_stale +
    summary.failed +
    summary.expensive +
    summary.zombie;

  if (totalIssues === 0) {
    return (
      <div className={styles.card}>
        <div className={styles.header}>
          <h2 className={styles.title}>Salud operativa</h2>
          <span className={styles.subtitle}>Escaneo de {summary.scanned} runs recientes</span>
        </div>
        <p className={styles.goodMessage}>✓ Todo en orden. No hay ejecuciones en triage.</p>
        <p className={styles.generatedAt}>
          Generado: {new Date(data.generated_at).toLocaleString()}
        </p>
      </div>
    );
  }

  const defaultOpenExecution = (id: number) => {
    // Si el padre no proporcionó callback, mostramos solo el ID.
    console.log(`Abrir ejecución #${id}`);
  };

  const handleOpenExecution = onOpenExecution || defaultOpenExecution;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Salud operativa</h2>
        <span className={styles.subtitle}>Escaneo de {summary.scanned} runs recientes</span>
      </div>

      <div className={styles.sectionsGrid}>
        <Section
          label="Por revisar"
          count={summary.needs_review_pending + summary.needs_review_stale}
          rows={data.needs_review}
          onOpenExecution={handleOpenExecution}
          sectionType="needs_review"
        />
        <Section
          label="Fallidas"
          count={summary.failed}
          rows={data.failed}
          onOpenExecution={handleOpenExecution}
          sectionType="failed"
        />
        <Section
          label="Caras"
          count={summary.expensive}
          rows={data.expensive}
          onOpenExecution={handleOpenExecution}
          sectionType="expensive"
        />
        <Section
          label="Zombies"
          count={summary.zombie}
          rows={data.zombie}
          onOpenExecution={handleOpenExecution}
          sectionType="zombie"
        />
      </div>

      <p className={styles.generatedAt}>
        Generado: {new Date(data.generated_at).toLocaleString()}
      </p>
    </div>
  );
}
