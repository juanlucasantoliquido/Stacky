/**
 * PipelineDoctorPanel (Plan 96 F4)
 * "¿Qué pasó?" — capa 1 (heurística, siempre) + capa 2 (agente DevOps, opcional).
 *
 * Estilos INLINE (no devops.module.css, que es WIP de otro plan en curso).
 */
import React, { useState } from 'react';
import { DevOps, DevOpsAgentApi } from '../../api/endpoints';
import { FlagGateBanner } from './FlagGateBanner';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import { buildAgentPrompt, summaryLine, type DoctorJob } from '../../devops/doctorModel';
import { useWorkbench } from '../../store/workbench';

export interface PipelineDoctorPanelProps {
  ctx: DevOpsSectionContext;
  project: string;
  pipelineId: string;
}

export const PipelineDoctorPanel: React.FC<PipelineDoctorPanelProps> = ({ ctx, project, pipelineId }) => {
  const [jobs, setJobs] = useState<DoctorJob[] | null>(null);
  const [failedJobsTotal, setFailedJobsTotal] = useState<number>(0);
  const [noFailuresFound, setNoFailuresFound] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);

  if (ctx.health.doctor_enabled !== true) {
    return (
      <FlagGateBanner
        flagKey="STACKY_DEVOPS_DOCTOR_ENABLED"
        flagLabel="Doctor de pipelines"
        message="Explicar en llano por qué falló el pipeline necesita el Doctor de pipelines (flag STACKY_DEVOPS_DOCTOR_ENABLED)."
        onEnabled={ctx.refetchHealth}
      />
    );
  }

  const handleDiagnose = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await DevOps.doctorDiagnose(project, pipelineId);
      setJobs(result.jobs);
      setFailedJobsTotal(result.failed_jobs_total);
      setNoFailuresFound(result.no_failures_found);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al diagnosticar el pipeline');
    } finally {
      setLoading(false);
    }
  };

  const handleExplainWithAgent = async () => {
    if (!jobs || jobs.length === 0) return;
    setAgentBusy(true);
    setAgentError(null);
    try {
      const message = buildAgentPrompt(project, jobs);
      const res = await DevOpsAgentApi.start({ project, message });
      setCodexConsoleExecution(res.execution_id);
    } catch (e: unknown) {
      setAgentError(e instanceof Error ? e.message : 'Error de red al abrir la conversación');
    } finally {
      setAgentBusy(false);
    }
  };

  return (
    <div style={{ marginTop: '16px', padding: '12px', borderRadius: '4px', border: '1px solid #444' }}>
      <h4 style={{ marginTop: 0 }}>¿Qué pasó?</h4>

      {!jobs && (
        <button onClick={() => void handleDiagnose()} disabled={loading} style={{ padding: '8px 16px' }}>
          {loading ? 'Diagnosticando...' : '¿Qué pasó?'}
        </button>
      )}

      {error && (
        <div style={{ marginTop: '8px', padding: '8px', borderRadius: '3px', fontSize: '13px', color: '#c0392b' }}>
          {error}
        </div>
      )}

      {jobs && (
        <div style={{ marginTop: '8px' }}>
          {noFailuresFound ? (
            <div style={{ fontSize: '13px' }}>No se encontraron jobs fallidos.</div>
          ) : (
            <>
              <div style={{ marginBottom: '8px', fontSize: '13px', fontWeight: 'bold' }}>
                {summaryLine(jobs)}
              </div>
              {failedJobsTotal > jobs.length && (
                <div style={{ marginBottom: '8px', padding: '6px', fontSize: '12px', color: '#b8860b' }}>
                  Mostrando {jobs.length} de {failedJobsTotal} jobs fallidos.
                </div>
              )}
              {jobs.map((job) => (
                <div
                  key={job.job_id}
                  style={{ marginBottom: '10px', padding: '8px', borderRadius: '3px', border: '1px solid #555' }}
                >
                  <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{job.name || job.job_id}</div>
                  {job.diagnosis.matches.length === 0 ? (
                    <div style={{ fontSize: '13px' }}>
                      No reconocí un patrón conocido — mirá el final del log.
                    </div>
                  ) : (
                    job.diagnosis.matches.map((match) => (
                      <div key={match.id} style={{ marginBottom: '4px', fontSize: '13px' }}>
                        <div>{match.title}</div>
                        <div style={{ fontSize: '12px', opacity: 0.8 }}>{match.hint}</div>
                      </div>
                    ))
                  )}
                  <details style={{ marginTop: '6px' }}>
                    <summary style={{ fontSize: '12px', cursor: 'pointer' }}>Ver fragmento del log</summary>
                    <pre style={{ marginTop: '4px', fontSize: '11px', whiteSpace: 'pre-wrap', maxHeight: '200px', overflow: 'auto' }}>
                      {job.diagnosis.snippet}
                    </pre>
                  </details>
                  {job.web_url != null && (
                    <div style={{ marginTop: '6px' }}>
                      <a href={job.web_url} target="_blank" rel="noreferrer" style={{ fontSize: '12px' }}>
                        Ver el log completo en el tracker
                      </a>
                    </div>
                  )}
                </div>
              ))}
              {ctx.health.agent_enabled === true && (
                <div style={{ marginTop: '8px' }}>
                  <button onClick={() => void handleExplainWithAgent()} disabled={agentBusy} style={{ padding: '8px 16px' }}>
                    {agentBusy ? 'Abriendo conversación...' : 'Explicar con el agente DevOps'}
                  </button>
                  {agentError && (
                    <div style={{ marginTop: '6px', fontSize: '12px', color: '#c0392b' }}>{agentError}</div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
};
