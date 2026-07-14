import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  DatabaseBackup,
  Download,
  RefreshCcw,
  XCircle,
} from "lucide-react";
import { LocalDiagnostics, type LocalDiagnosticCheck } from "../api/endpoints";
import HarnessHealthCard from "../components/HarnessHealthCard";
import OperationalHealthCard from "../components/OperationalHealthCard";
import CodeIntegrityCard from "../components/CodeIntegrityCard";
import ExecutionDetailDrawer from "../components/ExecutionDetailDrawer";
import styles from "./DiagnosticsPage.module.css";

const STATUS_LABEL = {
  ok: "OK",
  warning: "Atención",
  error: "Error",
} as const;

function StatusIcon({ status }: { status: LocalDiagnosticCheck["status"] }) {
  if (status === "ok") return <CheckCircle2 size={18} className={styles.okIcon} aria-hidden="true" />;
  if (status === "warning") return <AlertTriangle size={18} className={styles.warnIcon} aria-hidden="true" />;
  return <XCircle size={18} className={styles.errorIcon} aria-hidden="true" />;
}

function fmtBytes(value: number): string {
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

function fmtDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function DetailBlock({ detail }: { detail: unknown }) {
  if (!detail) return null;
  const text = typeof detail === "string" ? detail : JSON.stringify(detail, null, 2);
  return <pre className={styles.detail}>{text}</pre>;
}

export default function DiagnosticsPage() {
  const queryClient = useQueryClient();
  const [detailId, setDetailId] = useState<number | null>(null);

  const diagnostics = useQuery({
    queryKey: ["local-diagnostics"],
    queryFn: LocalDiagnostics.get,
    refetchInterval: 30_000,
  });

  const backup = useMutation({
    mutationFn: LocalDiagnostics.runBackup,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["local-diagnostics"] }),
  });

  const data = diagnostics.data;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleBlock}>
          <h2 className={styles.title}>Diagnóstico local</h2>
          <span className={styles.subtitle}>
            {data ? `Último chequeo ${fmtDate(data.checked_at)} · ${data.duration_ms} ms` : "Chequeando entorno local"}
          </span>
        </div>
        {data && (
          <div className={styles.summary} aria-label="Resumen de diagnóstico">
            <span className={`${styles.summaryBadge} ${styles.okBadge}`}>{data.summary.ok} OK</span>
            <span className={`${styles.summaryBadge} ${styles.warnBadge}`}>{data.summary.warning} atención</span>
            <span className={`${styles.summaryBadge} ${styles.errorBadge}`}>{data.summary.error} error</span>
          </div>
        )}
        <span className={styles.spacer} />
        <a
          href={LocalDiagnostics.exportLogsUrl()}
          className={styles.iconButton}
          title="Exportar logs"
          aria-label="Exportar logs"
        >
          <Download size={16} />
        </a>
        <button
          className={styles.iconButton}
          onClick={() => diagnostics.refetch()}
          disabled={diagnostics.isFetching}
          title="Actualizar diagnóstico"
          aria-label="Actualizar diagnóstico"
        >
          <RefreshCcw size={16} />
        </button>
      </header>

      {diagnostics.isError && (
        <section className={styles.errorPanel}>
          <XCircle size={18} />
          <span>{diagnostics.error instanceof Error ? diagnostics.error.message : "No se pudo cargar el diagnóstico."}</span>
        </section>
      )}

      <section className={styles.checkGrid}>
        {diagnostics.isLoading &&
          Array.from({ length: 6 }).map((_, index) => (
            <article className={styles.checkCard} key={index}>
              <span className={styles.skeletonIcon} />
              <div className={styles.skeletonLines}>
                <span />
                <span />
              </div>
            </article>
          ))}

        {data?.checks.map((check) => (
          <article className={styles.checkCard} key={check.id}>
            <div className={styles.checkHeader}>
              <StatusIcon status={check.status} />
              <div className={styles.checkTitleBlock}>
                <h3 className={styles.checkTitle}>{check.label}</h3>
                <span className={`${styles.statusPill} ${styles[check.status]}`}>
                  {STATUS_LABEL[check.status]}
                </span>
              </div>
            </div>
            <p className={styles.checkMessage}>{check.message}</p>
            <DetailBlock detail={check.detail} />
          </article>
        ))}
      </section>

      {data && (
        <section className={styles.opsGrid}>
          <div className={styles.opsPanel}>
            <div className={styles.panelHeader}>
              <Activity size={16} />
              <h3>Logs locales</h3>
              <a
                href={LocalDiagnostics.exportLogsUrl()}
                className={styles.textButton}
                title="Exportar logs"
                aria-label="Exportar logs"
              >
                <Download size={14} />
                Exportar ZIP
              </a>
            </div>
            <div className={styles.pathLine}>{data.logs.directory}</div>
            {data.logs.recent_files.length === 0 ? (
              <div className={styles.empty}>Sin archivos recientes.</div>
            ) : (
              <ul className={styles.fileList}>
                {data.logs.recent_files.map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
            )}
          </div>

          <div className={styles.opsPanel}>
            <div className={styles.panelHeader}>
              <DatabaseBackup size={16} />
              <h3>Backups DB</h3>
              <button
                className={styles.textButton}
                onClick={() => backup.mutate()}
                disabled={backup.isPending}
                title="Ejecutar backup"
                aria-label="Ejecutar backup"
              >
                <DatabaseBackup size={14} />
                {backup.isPending ? "Ejecutando" : "Ejecutar"}
              </button>
            </div>
            {backup.data && (
              <div className={backup.data.ok ? styles.inlineOk : styles.inlineError}>
                {backup.data.skipped ? backup.data.reason : backup.data.backup_path}
              </div>
            )}
            {data.backups.length === 0 ? (
              <div className={styles.empty}>Sin backups registrados.</div>
            ) : (
              <ul className={styles.backupList}>
                {data.backups.map((item) => (
                  <li key={item.path}>
                    <span>{item.filename}</span>
                    <strong>{fmtBytes(item.size_bytes)}</strong>
                    <em>{fmtDate(item.created_at)}</em>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {/* H8 — KPIs de valor agregado del arnés */}
      <HarnessHealthCard />

      {/* Plan 46 F3 — Panel de Salud Operativa (triage pasivo) */}
      <OperationalHealthCard onOpenExecution={setDetailId} />

      {/* Plan 130 — Verificador de integridad de código (on-demand) */}
      <CodeIntegrityCard />

      {/* Drawer para detalle de ejecución (Plan 38 C2) */}
      <ExecutionDetailDrawer executionId={detailId} onClose={() => setDetailId(null)} />
    </main>
  );
}
