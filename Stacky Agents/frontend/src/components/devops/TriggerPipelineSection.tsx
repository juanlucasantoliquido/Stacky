/**
 * TriggerPipelineSection (Plan 87 F5)
 * Trigger y monitor de pipelines CI (reusa CIPipeline, FIX C5)
 */
import React, { useState } from 'react';
import { CIPipeline, type CIPreviewResponse, type CITriggerResponse, type CIMonitorResponse } from '../../api/endpoints';
import { FlagGateBanner } from './FlagGateBanner';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';

export interface TriggerPipelineSectionProps {
  project: string;
  lastBranch: string; // FIX C6 - branch del último commit exitoso como default
}

export const TriggerPipelineSection: React.FC<TriggerPipelineSectionProps> = ({ project, lastBranch }) => {
  const [ref, setRef] = useState(lastBranch);
  const [previewData, setPreviewData] = useState<CIPreviewResponse | null>(null);
  const [triggerResult, setTriggerResult] = useState<CITriggerResponse | null>(null);
  const [polling, setPolling] = useState(false);
  const [pipelineId, setPipelineId] = useState<string | null>(null);
  const [monitorStatus, setMonitorStatus] = useState<CIMonitorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const ctx: DevOpsSectionContext = React.useMemo(() => ({
    health: { flag_enabled: true, generator_enabled: true, trigger_enabled: true },
    refetchHealth: () => {},
  }), []);

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
    <div style={{ marginTop: '16px', padding: '16px', backgroundColor: '#e7f3ff', borderRadius: '4px' }}>
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
          style={{ padding: '8px 16px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '4px' }}
        >
          Disparar
        </button>
      </div>

      {/* Preview HITL informado */}
      {previewData && (
        <div style={{ marginBottom: '12px', padding: '8px', backgroundColor: '#d1ecf1', border: '1px solid #bee5eb', borderRadius: '3px', fontSize: '13px' }}>
          <strong>Preview:</strong> ref resuelto = "{previewData.ref}"
          {previewData.would_reuse && (
            <span style={{ marginLeft: '8px', color: '#0c5460' }}>→ pipeline reciente reusado (idempotencia 60s)</span>
          )}
        </div>
      )}

      {/* Resultado del trigger */}
      {triggerResult && (
        <div style={{ marginBottom: '12px', padding: '8px', backgroundColor: '#d4edda', border: '1px solid #c3e6cb', borderRadius: '3px', fontSize: '13px' }}>
          <strong>Trigger exitoso:</strong> status = {triggerResult.status}
          {triggerResult.pipeline_id && (
            <span>, pipeline_id = {triggerResult.pipeline_id}</span>
          )}
        </div>
      )}

      {/* Monitoreo */}
      {monitorStatus && (
        <div style={{ marginBottom: '12px', padding: '8px', backgroundColor: '#fff3cd', border: '1px solid #ffc107', borderRadius: '3px', fontSize: '13px' }}>
          <strong>Estado:</strong>
          <pre style={{ margin: '4px 0 0 0', whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(monitorStatus, null, 2)}
          </pre>
        </div>
      )}

      {/* Errores */}
      {error && (
        <div style={{ marginBottom: '12px', padding: '8px', backgroundColor: '#f8d7da', border: '1px solid #f5c6cb', borderRadius: '3px', fontSize: '13px', color: '#721c24' }}>
          {error}
        </div>
      )}
    </div>
  );
};
