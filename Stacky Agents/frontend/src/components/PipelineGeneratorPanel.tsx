/**
 * PipelineGeneratorPanel.tsx — Plan 73 F5.
 * Editor de PipelineSpec + preview ADO/GitLab lado a lado + modal HITL para commit.
 */
import React, { useState } from 'react';

interface ValidationErrorItem {
  field: string;
  message: string;
}

interface PreviewResult {
  ado: string;
  gitlab: string;
  errors?: ValidationErrorItem[];
}

interface CommitResult {
  sha: string;
  branch: string;
  path: string;
  web_url: string;
  status: string;
  error?: string;
}

const DEFAULT_SPEC = JSON.stringify(
  {
    name: 'my-pipeline',
    stages: [
      {
        name: 'build',
        jobs: [
          {
            name: 'build-job',
            steps: [{ name: 'compile', script: 'make build' }],
            pool_vm_image: 'ubuntu-latest',
          },
        ],
      },
    ],
    trigger_branches: ['main'],
  },
  null,
  2
);

const API_BASE = '/api/pipeline-generator';

export const PipelineGeneratorPanel: React.FC = () => {
  const [specJson, setSpecJson] = useState<string>(DEFAULT_SPEC);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [validationErrors, setValidationErrors] = useState<ValidationErrorItem[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Modal HITL
  const [showCommitModal, setShowCommitModal] = useState(false);
  const [commitTarget, setCommitTarget] = useState<'gitlab' | 'ado'>('gitlab');
  const [commitBranch, setCommitBranch] = useState('');
  const [commitProject, setCommitProject] = useState('');
  const [commitLoading, setCommitLoading] = useState(false);
  const [commitResult, setCommitResult] = useState<CommitResult | null>(null);
  const [commitError, setCommitError] = useState<string>('');

  const handlePreview = async () => {
    setPreviewLoading(true);
    setValidationErrors([]);
    try {
      const spec = JSON.parse(specJson);
      const r = await fetch(`${API_BASE}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(spec),
      });
      const data = await r.json();
      if (!r.ok) {
        setValidationErrors(data.errors || [{ field: 'general', message: data.error || 'Error desconocido' }]);
        setPreview(null);
      } else {
        setPreview(data as PreviewResult);
        setValidationErrors([]);
      }
    } catch (e) {
      setValidationErrors([{ field: 'json', message: 'JSON inválido: ' + String(e) }]);
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleOpenCommitModal = () => {
    setCommitResult(null);
    setCommitError('');
    setShowCommitModal(true);
  };

  const handleConfirmCommit = async () => {
    setCommitLoading(true);
    setCommitError('');
    setCommitResult(null);
    try {
      const spec = JSON.parse(specJson);
      const payload: Record<string, unknown> = {
        ...spec,
        confirm: true, // HITL — obligatorio
        target: commitTarget,
        ...(commitBranch ? { branch: commitBranch } : {}),
        ...(commitProject ? { project: commitProject } : {}),
      };
      const r = await fetch(`${API_BASE}/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (!r.ok) {
        setCommitError(data.error || `Error ${r.status}`);
      } else {
        setCommitResult(data as CommitResult);
      }
    } catch (e) {
      setCommitError('Error de red: ' + String(e));
    } finally {
      setCommitLoading(false);
    }
  };

  return (
    <div style={{ padding: '1rem', fontFamily: 'sans-serif' }}>
      <h3 style={{ marginTop: 0 }}>Generador declarativo de pipelines</h3>

      {/* Editor del spec */}
      <div style={{ marginBottom: '0.75rem' }}>
        <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 600 }}>
          PipelineSpec (JSON)
        </label>
        <textarea
          rows={14}
          style={{ width: '100%', fontFamily: 'monospace', fontSize: 13, boxSizing: 'border-box' }}
          value={specJson}
          onChange={e => setSpecJson(e.target.value)}
          placeholder="Ingresá el PipelineSpec en JSON..."
        />
      </div>

      {/* Errores de validación */}
      {validationErrors.length > 0 && (
        <div style={{ background: '#fff3cd', border: '1px solid #ffc107', padding: '0.5rem', marginBottom: '0.5rem', borderRadius: 4 }}>
          {validationErrors.map((err, i) => (
            <div key={i}><strong>{err.field}:</strong> {err.message}</div>
          ))}
        </div>
      )}

      {/* Botones */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <button onClick={handlePreview} disabled={previewLoading}>
          {previewLoading ? 'Generando...' : 'Preview ADO + GitLab'}
        </button>
        <button onClick={handleOpenCommitModal} disabled={!preview}>
          Commitear...
        </button>
      </div>

      {/* Preview lado a lado */}
      {preview && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <h4 style={{ margin: '0 0 0.5rem' }}>azure-pipelines.yml (ADO)</h4>
            <pre style={{ background: '#f5f5f5', padding: '0.75rem', overflow: 'auto', fontSize: 12, borderRadius: 4, maxHeight: 300 }}>
              {preview.ado}
            </pre>
          </div>
          <div>
            <h4 style={{ margin: '0 0 0.5rem' }}>.gitlab-ci.yml (GitLab)</h4>
            <pre style={{ background: '#f5f5f5', padding: '0.75rem', overflow: 'auto', fontSize: 12, borderRadius: 4, maxHeight: 300 }}>
              {preview.gitlab}
            </pre>
          </div>
        </div>
      )}

      {/* Modal HITL */}
      {showCommitModal && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
        }}>
          <div style={{ background: '#fff', borderRadius: 8, padding: '1.5rem', minWidth: 380, maxWidth: 520 }}>
            <h4 style={{ margin: '0 0 1rem' }}>Commitear pipeline al repo</h4>

            <div style={{ background: '#fff3cd', border: '1px solid #ffc107', padding: '0.5rem', borderRadius: 4, marginBottom: '1rem', fontSize: 13 }}>
              ⚠️ Esto commitea un archivo real en el repo. Revisá el preview antes de confirmar.
            </div>

            <label style={{ display: 'block', marginBottom: '0.5rem' }}>
              Target:&nbsp;
              <select value={commitTarget} onChange={e => setCommitTarget(e.target.value as 'gitlab' | 'ado')}>
                <option value="gitlab">GitLab (.gitlab-ci.yml)</option>
                <option value="ado">ADO (azure-pipelines.yml) — render only v1</option>
              </select>
            </label>

            <label style={{ display: 'block', marginBottom: '0.5rem' }}>
              Branch (opcional):&nbsp;
              <input
                value={commitBranch}
                onChange={e => setCommitBranch(e.target.value)}
                placeholder="feature/pipeline-<slug>"
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </label>

            <label style={{ display: 'block', marginBottom: '1rem' }}>
              Proyecto (opcional):&nbsp;
              <input
                value={commitProject}
                onChange={e => setCommitProject(e.target.value)}
                placeholder="nombre-del-proyecto"
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </label>

            {commitError && (
              <div style={{ background: '#f8d7da', border: '1px solid #dc3545', padding: '0.5rem', borderRadius: 4, marginBottom: '0.75rem', fontSize: 13 }}>
                {commitError}
              </div>
            )}

            {commitResult && (
              <div style={{ background: '#d1e7dd', border: '1px solid #198754', padding: '0.5rem', borderRadius: 4, marginBottom: '0.75rem', fontSize: 13 }}>
                {commitResult.status === 'unchanged'
                  ? 'Sin cambios — el archivo ya era idéntico.'
                  : <>Commit OK: <a href={commitResult.web_url} target="_blank" rel="noreferrer">{commitResult.sha || 'ver'}</a> en {commitResult.branch}</>
                }
              </div>
            )}

            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
              <button onClick={() => setShowCommitModal(false)}>Cancelar</button>
              <button
                onClick={handleConfirmCommit}
                disabled={commitLoading || !!commitResult}
                style={{ background: '#dc3545', color: '#fff', border: 'none', padding: '0.4rem 1rem', borderRadius: 4, cursor: 'pointer' }}
              >
                {commitLoading ? 'Commiteando...' : 'Confirmar commit'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PipelineGeneratorPanel;
