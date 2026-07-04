/**
 * PipelineYamlPreview (Plan 87 F5)
 * Preview vivo de YAML ADO y GitLab con FlagGateBanner (C14) y auto-refresh (C17)
 */
import React, { useState, useEffect } from 'react';
import { PipelineGenerator } from '../../api/endpoints';
import { FlagGateBanner } from './FlagGateBanner';
import { toSpecDict, type PipelineSpecDraft } from '../../devops/specBuilder';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';

export interface PipelineYamlPreviewProps {
  spec: PipelineSpecDraft;
  ctx: DevOpsSectionContext;
  localErrors: string[];
}

export const PipelineYamlPreview: React.FC<PipelineYamlPreviewProps> = ({ spec, ctx, localErrors }) => {
  const [preview, setPreview] = useState<{ ado: string; gitlab: string } | null>(null);
  const [previewErrors, setPreviewErrors] = useState<Array<{ field: string; message: string }>>([]);
  const [loading, setLoading] = useState(false);

  // Refrescar preview manual o auto
  const refreshPreview = async () => {
    if (localErrors.length > 0) return; // No preview si hay errores locales
    setLoading(true);
    setPreviewErrors([]);
    try {
      const result = await PipelineGenerator.preview(toSpecDict(spec));
      setPreview(result);
    } catch (e: unknown) {
      // 400 con errors
      if (e && typeof e === 'object' && 'errors' in e) {
        setPreviewErrors((e.errors as Array<{ field: string; message: string }>));
      } else {
        setPreviewErrors([{ field: 'general', message: e instanceof Error ? e.message : 'Error desconocido' }]);
      }
    } finally {
      setLoading(false);
    }
  };

  // C17 - auto-refresh con debounce de 800ms tras el último cambio del spec
  // (solo si generator_enabled y sin errores locales; el botón manual sigue
  // siempre disponible más abajo).
  useEffect(() => {
    if (!ctx.health.generator_enabled || localErrors.length > 0) return;
    const timeoutId = setTimeout(() => {
      void refreshPreview();
    }, 800);
    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec, ctx.health.generator_enabled, localErrors.length]);

  // C14 - FlagGateBanner si generator_enabled=false
  if (!ctx.health.generator_enabled) {
    return (
      <FlagGateBanner
        flagKey="STACKY_PIPELINE_GENERATOR_ENABLED"
        flagLabel="Generador de pipelines"
        message="El preview y el commit necesitan el Generador de pipelines (flag STACKY_PIPELINE_GENERATOR_ENABLED, categoría 'Épicas, briefs y publicación en ADO')."
        onEnabled={ctx.refetchHealth}
      />
    );
  }

  return (
    <div style={{ padding: '16px', backgroundColor: '#f8f9fa', borderRadius: '4px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <h3 style={{ margin: 0 }}>Preview YAML</h3>
        <button
          onClick={() => void refreshPreview()}
          disabled={loading || localErrors.length > 0}
          title={localErrors.length > 0 ? 'Resolvé los avisos primero' : undefined}
          style={{ padding: '6px 12px', fontSize: '12px' }}
        >
          {loading ? 'Actualizando...' : 'Actualizar preview'}
        </button>
      </div>

      {/* C12 - errores locales visibles */}
      {localErrors.length > 0 && (
        <div style={{ marginBottom: '12px', padding: '8px', backgroundColor: '#fff3cd', border: '1px solid #ffc107', borderRadius: '3px' }}>
          <strong>Antes del preview:</strong>
          <ul style={{ margin: '4px 0 0 20px', padding: 0 }}>
            {localErrors.map((err, i) => (
              <li key={i} style={{ fontSize: '13px', color: '#856404' }}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Errores del backend */}
      {previewErrors.length > 0 && (
        <div style={{ marginBottom: '12px', padding: '8px', backgroundColor: '#f8d7da', border: '1px solid #f5c6cb', borderRadius: '3px' }}>
          <strong>Errores de validación:</strong>
          <ul style={{ margin: '4px 0 0 20px', padding: 0 }}>
            {previewErrors.map((err, i) => (
              <li key={i} style={{ fontSize: '13px', color: '#721c24' }}>
                {err.field ? `${err.field}: ` : ''}{err.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Preview lado a lado */}
      {preview && (
        <div style={{ display: 'flex', gap: '16px' }}>
          <div style={{ flex: 1 }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: '14px' }}>Azure DevOps</h4>
            <pre
              style={{
                backgroundColor: 'white',
                border: '1px solid #dee2e6',
                borderRadius: '3px',
                padding: '8px',
                fontSize: '11px',
                maxHeight: '400px',
                overflow: 'auto',
                margin: 0,
              }}
            >
              {preview.ado}
            </pre>
          </div>
          <div style={{ flex: 1 }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: '14px' }}>GitLab CI</h4>
            <pre
              style={{
                backgroundColor: 'white',
                border: '1px solid #dee2e6',
                borderRadius: '3px',
                padding: '8px',
                fontSize: '11px',
                maxHeight: '400px',
                overflow: 'auto',
                margin: 0,
              }}
            >
              {preview.gitlab}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};
