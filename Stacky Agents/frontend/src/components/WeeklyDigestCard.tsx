import { useQuery } from "@tanstack/react-query";
import { Reports } from "../api/endpoints";
import styles from "./WeeklyDigestCard.module.css";

interface Props {
  /** Proyecto opcional para acotar el digest; sin valor = todos los proyectos. */
  project?: string;
  /** Ventana en días (default 7 = "reporte semanal"). */
  days?: number;
}

function pct(rate: number): string {
  return `${(rate * 100).toFixed(0)}%`;
}

function usd(n: number): string {
  if (!n) return "$0";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  if (n < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}

interface KpiProps {
  label: string;
  value: string | number;
  sub?: string;
}

function Kpi({ label, value, sub }: KpiProps) {
  return (
    <div className={styles.kpi}>
      <div className={styles.kpiLabel}>{label}</div>
      <div className={styles.kpiValue}>{value}</div>
      {sub && <div className={styles.kpiSub}>{sub}</div>}
    </div>
  );
}

export default function WeeklyDigestCard({ project, days = 7 }: Props) {
  const digestQ = useQuery({
    queryKey: ["reports.digest", days, project ?? null],
    queryFn: () => Reports.digest({ days, project }),
    staleTime: 60_000,
  });

  const digest = digestQ.data ?? null;
  const totals = digest?.totals ?? null;
  const hasActivity = !!totals && totals.runs > 0;

  // URLs de descarga directa (siempre disponibles, aun sin actividad).
  const mdUrl = Reports.digestDownloadUrl({ fmt: "md", days, project });
  const htmlUrl = Reports.digestDownloadUrl({ fmt: "html", days, project });

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h3 className={styles.title}>📈 Reporte semanal</h3>
        <span className={styles.meta}>últimos {days} días</span>
        {digest?.partial && (
          <span
            className={styles.partial}
            title="Incluye costos estimados: no todos los runtimes reportan costo real"
          >
            incluye estimados
          </span>
        )}
        <div className={styles.actions}>
          <a className={styles.btn} href={mdUrl} download title="Descargar Markdown">
            ⬇ MD
          </a>
          <a className={styles.btn} href={htmlUrl} download title="Descargar HTML">
            ⬇ HTML
          </a>
        </div>
      </div>

      {digestQ.isLoading ? (
        <div className={styles.empty}>Cargando reporte…</div>
      ) : digestQ.isError ? (
        <div className={styles.empty}>No se pudo cargar el reporte.</div>
      ) : hasActivity ? (
        <>
          <div className={styles.grid}>
            <Kpi label="Runs" value={totals!.runs} />
            <Kpi
              label="Éxito sin intervención"
              value={pct(totals!.success_rate)}
              sub={`${totals!.completed} completados`}
            />
            <Kpi
              label="Necesitan revisión"
              value={totals!.needs_review}
              sub={`${totals!.error} con error`}
            />
            <Kpi
              label="Costo total"
              value={usd(totals!.cost_usd.total)}
              sub={
                totals!.cost_usd.estimated > 0
                  ? `${usd(totals!.cost_usd.reported)} real + estimado`
                  : undefined
              }
            />
            <Kpi label="Tickets tocados" value={totals!.tickets_touched} />
          </div>
          {digest!.highlights.length > 0 && (
            <ul className={styles.highlights}>
              {digest!.highlights.map((h, i) => (
                <li key={i}>{h}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className={styles.empty}>Sin actividad en el período.</div>
      )}
    </section>
  );
}
