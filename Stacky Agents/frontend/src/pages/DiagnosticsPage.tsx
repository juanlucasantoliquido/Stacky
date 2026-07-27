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
import { Health, LocalDiagnostics, type LocalDiagnosticCheck } from "../api/endpoints";
import HarnessHealthCard from "../components/HarnessHealthCard";
import PublishLedgerPanel from "../components/PublishLedgerPanel";
import OperationalHealthCard from "../components/OperationalHealthCard";
import CodeIntegrityCard from "../components/CodeIntegrityCard";
import RunReconciliationCard from "../components/RunReconciliationCard";
import SilentFailuresCard from "../components/SilentFailuresCard";
import DormantCanariesCard from "../components/DormantCanariesCard";
import IntakeQuarantineCard from "../components/IntakeQuarantineCard";
import ParityMatrixPanel from "../components/ParityMatrixPanel";
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

const WAL_STATUS_LABEL: Record<string, string> = {
  ok: "activa (lectura y escritura simultáneas)",
  in_memory: "base en memoria (no aplica)",
  rejected: "el disco la rechazó — puede haber bloqueos",
  disabled: "desactivada por configuración",
  not_sqlite: "no aplica a este motor",
  unknown: "sin determinar todavía",
};

/**
 * Plan 253 F7 — estado REAL de la concurrencia de la base, en solo lectura.
 * Sin polling propio: se consulta una vez al abrir el panel. Si el servidor es
 * viejo y no manda el bloque, la tarjeta simplemente no se muestra.
 */
function DbRuntimeCard() {
  const health = useQuery({
    queryKey: ["diag-health-db-runtime"],
    queryFn: Health.get,
    staleTime: 60_000,
  });
  const rt = health.data?.db_runtime;
  if (!rt) return null;

  const rows: Array<[string, string]> = [
    ["Lectura/escritura simultáneas", WAL_STATUS_LABEL[rt.wal_status] ?? rt.wal_status],
    ["Modo de registro efectivo", rt.journal_mode_effective ?? "—"],
    ["Espera máxima ante bloqueo", rt.busy_timeout_ms == null ? "—" : `${rt.busy_timeout_ms} ms`],
    ["Confirmación a disco", rt.synchronous === 1 ? "NORMAL (rápida)" : "FULL (durable)"],
    ["Tamaño de la base", rt.db_size_bytes == null ? "—" : fmtBytes(rt.db_size_bytes)],
    ["Tamaño del archivo auxiliar", fmtBytes(rt.wal_size_bytes ?? 0)],
    ["Carga inicial", rt.startup_writes.done ? "terminada" : "en curso"],
    [
      "Bloqueos",
      `${rt.lock_stats.retried} reintentos · ${rt.lock_stats.recovered} recuperados · ` +
        `${rt.lock_stats.exhausted} perdidos`,
    ],
    ["Arranques contabilizados", rt.create_app_count == null ? "—" : String(rt.create_app_count)],
  ];
  for (const [name, info] of Object.entries(rt.maintenance ?? {})) {
    rows.push([
      `Mantenimiento: ${name}`,
      info.last_error
        ? `último error: ${info.last_error}`
        : `${info.last_count} unidades en la última pasada`,
    ]);
  }

  return (
    <section className={styles.opsPanel}>
      <div className={styles.panelHeader}>
        <DatabaseBackup size={16} aria-hidden="true" />
        <h3>Base de datos: concurrencia y mantenimiento</h3>
      </div>
      <ul className={styles.fileList}>
        {rows.map(([label, value]) => (
          <li key={label}>
            {label}: {value}
          </li>
        ))}
      </ul>
      {rt.sqlite_file ? <p className={styles.pathLine}>{rt.sqlite_file}</p> : null}
    </section>
  );
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

      {/* Plan 253 F7 — concurrencia de la base, consultable (solo lectura) */}
      <DbRuntimeCard />

      {/* H8 — KPIs de valor agregado del arnés */}
      <HarnessHealthCard />

      {/* Plan 153 — Ledger de publicaciones ADO: desbloqueo humano 1-click */}
      <PublishLedgerPanel />

      {/* Plan 46 F3 — Panel de Salud Operativa (triage pasivo) */}
      <OperationalHealthCard onOpenExecution={setDetailId} />

      {/* Plan 130 — Verificador de integridad de código (on-demand) */}
      <CodeIntegrityCard />

      {/* Plan 254 F5 — el falso ROJO, medido. READ-ONLY: lista, no cambia nada.
          No se monta si STACKY_RUN_RECONCILIATION_ENABLED está apagada (404). */}
      <RunReconciliationCard />

      {/* Plan 255 F1 — el silencio, contado. READ-ONLY sobre un dict en memoria;
          declara su ventana porque un cero NO prueba que un punto sea inerte.
          No se monta si STACKY_SILENT_FAILURE_COUNTER_ENABLED está apagada (404). */}
      <SilentFailuresCard />

      {/* Plan 255 F6 — mecanismos caros que dejaron de dar señal de ÉXITO.
          AVISA, nunca arregla. No se monta si STACKY_DORMANT_CANARY_ENABLED
          está apagada (404). */}
      <DormantCanariesCard />

      {/* Plan 256 F3 — artefactos entregados por un agente que quedaron apartados
          por el intake, con el motivo COMPLETO y hace cuántos días. No se monta si
          no hay ninguno o si STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED está apagada. */}
      <IntakeQuarantineCard />

      {/* Plan 218 F8 — Paridad del tracker (ADO ↔ GitLab). No se monta si la flag
          maestra STACKY_PROVIDER_PARITY_ENABLED está apagada (el endpoint da 404). */}
      <ParityMatrixPanel />

      {/* Drawer para detalle de ejecución (Plan 38 C2) */}
      <ExecutionDetailDrawer executionId={detailId} onClose={() => setDetailId(null)} />
    </main>
  );
}
