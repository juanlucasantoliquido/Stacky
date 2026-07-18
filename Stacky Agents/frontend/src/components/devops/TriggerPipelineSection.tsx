/**
 * TriggerPipelineSection (Plan 87 F5)
 * Trigger y monitor de pipelines CI (reusa CIPipeline, FIX C5)
 */
import React, { useState } from 'react';
import {
  CIPipeline,
  type CIPreviewResponse,
  type CITriggerResponse,
  type CIMonitorResponse,
  type JobLogResponse,
} from '../../api/endpoints';
import { FlagGateBanner } from './FlagGateBanner';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import { PipelineDoctorPanel } from './PipelineDoctorPanel';
import {
  pollTargets,
  retriggerPayload,
  runLabel,
  effectiveStatus,
  POLL_INTERVAL_MS,
  type CiRun,
} from './ciRunsLedger';
import {
  jobLabel,
  logFileName,
  truncationNote,
  errorLineHints,
  EMPTY_FAILED_JOBS_MSG,
  type FailedJob,
} from './ciFailureTriage';
import styles from './devops.module.css';

// ── Plan 193 · Fila de un job fallido: log inline enmascarado, lazy al expandir ──
interface JobLogState {
  loading: boolean;
  error: string | null;
  data: JobLogResponse | null;
}

const FailedJobRow: React.FC<{ project: string; job: FailedJob }> = ({ project, job }) => {
  const [state, setState] = useState<JobLogState>({ loading: false, error: null, data: null });
  const preRef = React.useRef<HTMLPreElement | null>(null);

  const log = state.data?.log ?? '';
  const hints = React.useMemo(() => (log ? errorLineHints(log) : []), [log]);

  const loadLog = React.useCallback(async () => {
    setState({ loading: true, error: null, data: null });
    try {
      const data = await CIPipeline.jobLog(project, job.job_id);
      setState({ loading: false, error: null, data });
    } catch (e: unknown) {
      setState({
        loading: false,
        error: e instanceof Error ? e.message : 'No se pudo cargar el log del job',
        data: null,
      });
    }
  }, [project, job.job_id]);

  // Fetch SOLO al expandir (lazy; sin N+1).
  const handleToggle = (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    if (e.currentTarget.open && !state.data && !state.loading && !state.error) {
      void loadLog();
    }
  };

  const scrollToFirstError = React.useCallback(() => {
    const pre = preRef.current;
    if (!pre || hints.length === 0) return;
    const totalLines = log.split('\n').length || 1;
    pre.scrollTop = ((hints[0] - 1) / totalLines) * pre.scrollHeight;
  }, [hints, log]);

  // [ADICIÓN ARQUITECTO] auto-scroll a la primera línea con error cuando llega el log.
  React.useEffect(() => {
    if (state.data && hints.length > 0) scrollToFirstError();
  }, [state.data, hints, scrollToFirstError]);

  const handleDownload = () => {
    if (!state.data) return;
    const blob = new Blob([state.data.log], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = logFileName(job.job_id);
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url); // C4 — sin fuga de memoria en sesiones largas.
  };

  const note = state.data ? truncationNote(state.data.truncated, state.data.chars_total) : null;

  return (
    <details className={styles.ciTriageJob} onToggle={handleToggle}>
      <summary className={styles.ciTriageJobSummary}>
        <span className={styles.ciTriageJobLabel}>{jobLabel(job)}</span>
        {job.web_url && (
          <a
            className={styles.ciRunOpen}
            href={job.web_url}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
          >
            abrir en el tracker
          </a>
        )}
      </summary>
      {state.loading && <div className={styles.ciTriageMuted}>Cargando log…</div>}
      {state.error && <div className={styles.alertError}>{state.error}</div>}
      {state.data && (
        <div className={styles.ciTriageLogWrap}>
          <div className={styles.ciTriageLogBar}>
            {hints.length > 0 && (
              <button type="button" className={styles.ciTriageErrChip} onClick={scrollToFirstError}>
                {hints.length} líneas con error
              </button>
            )}
            <button type="button" className={styles.ciTriageDownload} onClick={handleDownload}>
              Descargar
            </button>
          </div>
          {note && <div className={styles.ciTriageMuted}>{note}</div>}
          <pre ref={preRef} className={styles.ciTriageLog}>{state.data.log}</pre>
        </div>
      )}
    </details>
  );
};

export interface TriggerPipelineSectionProps {
  ctx: DevOpsSectionContext; // Plan 96 — necesario para gatear PipelineDoctorPanel
  project: string;
  lastBranch: string; // FIX C6 - branch del último commit exitoso como default
}

export const TriggerPipelineSection: React.FC<TriggerPipelineSectionProps> = ({ ctx, project, lastBranch }) => {
  const [ref, setRef] = useState(lastBranch);
  const [previewData, setPreviewData] = useState<CIPreviewResponse | null>(null);
  const [triggerResult, setTriggerResult] = useState<CITriggerResponse | null>(null);
  const [polling, setPolling] = useState(false);
  const [pipelineId, setPipelineId] = useState<string | null>(null);
  const [monitorStatus, setMonitorStatus] = useState<CIMonitorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Plan 191 — bitácora de corridas CI (historial con estado vivo + re-disparo HITL).
  const [runs, setRuns] = useState<CiRun[]>([]);
  const [statusById, setStatusById] = useState<Record<string, string | undefined>>({});
  const [ledgerAvailable, setLedgerAvailable] = useState(true);

  // Plan 193 — triage de fallos CI (jobs fallidos + log inline enmascarado, read-only).
  const [triageJobs, setTriageJobs] = useState<FailedJob[] | null>(null);
  const [triageError, setTriageError] = useState<string | null>(null);
  const [triageLoading, setTriageLoading] = useState(false);
  const [triageAvailable, setTriageAvailable] = useState(true);

  const loadFailedJobs = React.useCallback(async () => {
    if (!pipelineId) return;
    setTriageLoading(true);
    setTriageError(null);
    try {
      const data = await CIPipeline.failedJobs(project, pipelineId);
      setTriageJobs(data.jobs);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '';
      // 404 (flag OFF) → ocultar el botón el resto de la sesión; otro error → inline.
      if (/^404\b/.test(msg)) {
        setTriageAvailable(false);
      } else {
        setTriageError('No se pudieron listar los jobs fallidos');
      }
    } finally {
      setTriageLoading(false);
    }
  }, [project, pipelineId]);

  // Al cambiar de pipeline monitoreado, resetear el triage (evita mostrar jobs viejos).
  React.useEffect(() => {
    setTriageJobs(null);
    setTriageError(null);
  }, [pipelineId]);

  const loadRuns = React.useCallback(async () => {
    try {
      const data = await CIPipeline.runs(project, 20);
      setRuns(data.runs as CiRun[]);
    } catch {
      // 404 (flag OFF) u otro error → sección idéntica a hoy; no reintentar en la sesión.
      setLedgerAvailable(false);
    }
  }, [project]);

  React.useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  // Poll de estado acotado (KPI-4): solo los ids no-finales, cap 5, cada 10 s; se
  // detiene cuando todos terminaron. Reusa el monitor existente /pipeline/<id>.
  React.useEffect(() => {
    if (!ledgerAvailable) return;
    const targets = pollTargets(runs, statusById);
    if (targets.length === 0) return;
    const interval = setInterval(() => {
      targets.forEach((id) => {
        CIPipeline.monitor(project, id)
          .then((s) => setStatusById((prev) => ({ ...prev, [id]: s.status })))
          .catch(() => { /* best-effort: un poll fallido no rompe la UI */ });
      });
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [runs, statusById, ledgerAvailable, project]);

  // Re-disparar: PRECARGA el ref en el formulario; el operador confirma con "Disparar"
  // (flujo HITL existente). NUNCA dispara por sí solo (sin confirm automático).
  const handleRetrigger = (run: CiRun) => {
    setRef(retriggerPayload(run).ref);
    setError(null);
  };

  // C14 - FlagGateBanner si trigger_enabled=false (esto no debería pasar porque el padre ya chequea)
  if (!ctx.health.trigger_enabled) {
    return (
      <FlagGateBanner
        flagKey="STACKY_PIPELINE_TRIGGER_ENABLED"
        flagLabel="Trigger CI"
        message="Disparar y monitorear pipelines necesita el Trigger CI (flag STACKY_PIPELINE_TRIGGER_ENABLED, categoría 'Épicas, briefs y publicación en ADO')."
        onEnabled={ctx.refetchHealth}
      />
    );
  }

  const handlePreview = async () => {
    if (!ref.trim()) {
      setError('El ref es obligatorio');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await CIPipeline.preview(project, ref);
      setPreviewData(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al hacer preview');
    } finally {
      setLoading(false);
    }
  };

  const handleTrigger = async () => {
    if (!ref.trim()) {
      setError('El ref es obligatorio');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await CIPipeline.trigger(project, ref, '', '', true);
      setTriggerResult(result);
      if (result.pipeline_id) {
        setPipelineId(result.pipeline_id);
        setPolling(true);
      }
      void loadRuns(); // Plan 191 — refrescar la bitácora tras el disparo
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al disparar');
    } finally {
      setLoading(false);
    }
  };

  const handleMonitor = async () => {
    if (!pipelineId) return;
    try {
      const status = await CIPipeline.monitor(project, pipelineId);
      setMonitorStatus(status);
      // Si terminó, parar polling
      if (['success', 'failed', 'canceled'].includes(status.status)) {
        setPolling(false);
      }
    } catch (e: unknown) {
      setPolling(false);
      setError(e instanceof Error ? e.message : 'Error al monitorear');
    }
  };

  // Auto-polling si está activo
  React.useEffect(() => {
    if (polling && pipelineId) {
      const interval = setInterval(() => {
        void handleMonitor();
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [polling, pipelineId]);

  return (
    <div className={styles.panelMuted} style={{ marginTop: '16px' }}>
      <h3 style={{ marginTop: 0 }}>Trigger CI</h3>

      <div style={{ marginBottom: '12px' }}>
        <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Ref (branch/tag/commit)</label>
        <input
          type="text"
          value={ref}
          onChange={(e) => setRef(e.target.value)}
          placeholder="main, feature/pipeline-x, v1.2.3..."
          disabled={loading}
          style={{ width: '100%', padding: '8px' }}
        />
      </div>

      <div style={{ marginBottom: '12px', display: 'flex', gap: '8px' }}>
        <button
          onClick={() => void handlePreview()}
          disabled={loading}
          style={{ padding: '8px 16px' }}
        >
          Preview
        </button>
        <button
          onClick={() => void handleTrigger()}
          disabled={loading}
          className={styles.btnPrimary}
        >
          Disparar
        </button>
      </div>

      {/* Preview HITL informado */}
      {previewData && (
        <div className={styles.alertInfo} style={{ marginBottom: '12px', padding: '8px', borderRadius: '3px', fontSize: '13px' }}>
          <strong>Preview:</strong> ref resuelto = "{previewData.ref}"
          {previewData.would_reuse && (
            <span style={{ marginLeft: '8px' }}>→ pipeline reciente reusado (idempotencia 60s)</span>
          )}
        </div>
      )}

      {/* Resultado del trigger */}
      {triggerResult && (
        <div className={styles.alertSuccess} style={{ marginBottom: '12px', padding: '8px', borderRadius: '3px', fontSize: '13px' }}>
          <strong>Trigger exitoso:</strong> status = {triggerResult.status}
          {triggerResult.pipeline_id && (
            <span>, pipeline_id = {triggerResult.pipeline_id}</span>
          )}
        </div>
      )}

      {/* Monitoreo */}
      {monitorStatus && (
        <div className={styles.alertWarning} style={{ marginBottom: '12px', padding: '8px', borderRadius: '3px', fontSize: '13px' }}>
          <strong>Estado:</strong>
          <pre style={{ margin: '4px 0 0 0', whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(monitorStatus, null, 2)}
          </pre>
        </div>
      )}

      {/* Plan 193 — Triage determinista: jobs fallidos + log inline enmascarado (read-only).
          Capa PREVIA al Doctor IA (96); aparece SOLO con el pipeline fallido. */}
      {monitorStatus?.status === 'failed' && pipelineId && triageAvailable && (
        <div className={styles.ciTriageSection}>
          {triageJobs === null ? (
            <button
              type="button"
              className={styles.ciTriageBtn}
              onClick={() => void loadFailedJobs()}
              disabled={triageLoading}
            >
              {triageLoading ? 'Cargando…' : 'Ver fallos…'}
            </button>
          ) : triageJobs.length === 0 ? (
            <div className={styles.ciTriageEmpty}>{EMPTY_FAILED_JOBS_MSG}</div>
          ) : (
            <div className={styles.ciTriageList}>
              {triageJobs.map((job) => (
                <FailedJobRow key={job.job_id} project={project} job={job} />
              ))}
            </div>
          )}
          {triageError && (
            <div className={`${styles.alertError} ${styles.ciTriageErr}`}>{triageError}</div>
          )}
        </div>
      )}

      {/* Doctor de pipelines (Plan 96) — solo cuando el pipeline falló */}
      {monitorStatus?.status === 'failed' && pipelineId && (
        <PipelineDoctorPanel ctx={ctx} project={project} pipelineId={pipelineId} />
      )}

      {/* Errores */}
      {error && (
        <div className={styles.alertError} style={{ marginBottom: '12px', padding: '8px', borderRadius: '3px', fontSize: '13px' }}>
          {error}
        </div>
      )}

      {/* Plan 191 — Bitácora de corridas CI (historial con estado vivo + re-disparo HITL) */}
      {ledgerAvailable && (
        <div className={styles.ciRunsSection}>
          <h4 className={styles.ciRunsHeading}>Historial de corridas</h4>
          {runs.length === 0 ? (
            <div className={styles.ciRunsEmpty}>Sin corridas registradas todavía.</div>
          ) : (
            <div className={styles.ciRunsList}>
              {runs.map((run) => (
                <div key={`${run.pipeline_id}-${run.triggered_at}`} className={styles.ciRunRow}>
                  <span className={styles.ciRunLabel} title={runLabel(run)}>{runLabel(run)}</span>
                  <span className={styles.ciRunChip}>{effectiveStatus(run, statusById)}</span>
                  <span className={styles.ciRunActions}>
                    {run.web_url && (
                      <a
                        className={styles.ciRunOpen}
                        href={run.web_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        abrir
                      </a>
                    )}
                    <button
                      type="button"
                      className={styles.ciRunRetrigger}
                      onClick={() => handleRetrigger(run)}
                      disabled={loading}
                      title="Precarga el ref; confirmá con Disparar (HITL)"
                    >
                      Re-disparar…
                    </button>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
