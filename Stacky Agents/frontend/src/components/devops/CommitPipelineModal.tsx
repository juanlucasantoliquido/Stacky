/**
 * CommitPipelineModal (Plan 87 F5)
 * Modal de commit HITL con checkbox de confirmación obligatorio
 */
import React, { useState } from 'react';
import { PipelineGenerator } from '../../api/endpoints';
import { toSpecDict, type PipelineSpecDraft } from '../../devops/specBuilder';
import styles from './devops.module.css';

export interface CommitPipelineModalProps {
  spec: PipelineSpecDraft;
  project: string;
  onSuccess: (branch: string) => void;
  onClose: () => void;
  /**
   * Plan 95 [C2]: capability aditiva del health (`ado_commit_supported`), NO la
   * flag `production_enabled` -- existe solo en builds que incluyen la F1 del
   * plan 95 (commit ADO real). Contra un backend viejo la key está ausente ⇒
   * este prop llega `false`/`undefined` ⇒ el modal queda IDÉNTICO a hoy.
   */
  adoCommitSupported?: boolean;
}

export const CommitPipelineModal: React.FC<CommitPipelineModalProps> = ({
  spec,
  project,
  onSuccess,
  onClose,
  adoCommitSupported = false,
}) => {
  const [target, setTarget] = useState<'gitlab' | 'ado'>('gitlab');
  const [branch, setBranch] = useState('');
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ ok: true; data: Record<string, unknown> } | { ok: false; error: string } | null>(null);

  const handleSubmit = async () => {
    if (!confirmChecked) return;
    setLoading(true);
    setResult(null);
    try {
      const response = await PipelineGenerator.commit({
        ...toSpecDict(spec),
        target,
        branch: branch || undefined, // Backend deriva si está vacío
        project,
        confirm: true,
      });
      setResult({ ok: true, data: response as Record<string, unknown> });
      // Guardar el branch usado para ofrecerlo en trigger
      if (response && typeof response === 'object' && 'branch' in response) {
        onSuccess(response.branch as string);
      }
    } catch (e: unknown) {
      setResult({ ok: false, error: e instanceof Error ? e.message : 'Error desconocido' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modalBody}>
        <h3 style={{ marginTop: 0 }}>Commit Pipeline al Repositorio</h3>

        {(!result || result.ok === false) && (
          <>
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Target</label>
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value as 'gitlab' | 'ado')}
                disabled={loading}
                style={{ width: '100%', padding: '8px' }}
              >
                <option value="gitlab">GitLab CI (.gitlab-ci.yml)</option>
                {adoCommitSupported ? (
                  <option value="ado" title="commit ADO habilitado por el plan 95">
                    Azure DevOps (azure-pipelines.yml)
                  </option>
                ) : (
                  <option value="ado" disabled>
                    Azure DevOps (pipeline.yml) — Render-only v1 (commit devuelve 501)
                  </option>
                )}
              </select>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Branch</label>
              <input
                type="text"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="feature/pipeline-nombre (vacío = backend deriva)"
                disabled={loading}
                style={{ width: '100%', padding: '8px' }}
              />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Project</label>
              <input
                type="text"
                value={project}
                disabled
                className={styles.inputDisabled}
                style={{ width: '100%', padding: '8px' }}
              />
            </div>

            <div className={styles.panelMuted} style={{ marginBottom: '16px', padding: '12px', borderRadius: '3px' }}>
              <label style={{ display: 'flex', alignItems: 'start', gap: '8px', cursor: loading ? 'not-allowed' : 'pointer' }}>
                <input
                  type="checkbox"
                  checked={confirmChecked}
                  onChange={(e) => setConfirmChecked(e.target.checked)}
                  disabled={loading}
                  style={{ marginTop: '2px' }}
                />
                <span style={{ fontSize: '14px' }}>
                  <strong>Confirmo el commit de este pipeline al repositorio.</strong>
                  Esta acción creará/actualizará el archivo de YAML en el branch especificado.
                </span>
              </label>
            </div>

            {result && result.ok === false && (
              <div className={styles.alertError} style={{ marginBottom: '16px', padding: '8px', borderRadius: '3px', fontSize: '13px' }}>
                {result.error}
              </div>
            )}

            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: 'auto' }}>
              <button onClick={onClose} disabled={loading} style={{ padding: '8px 16px' }}>
                Cancelar
              </button>
              <button
                onClick={() => void handleSubmit()}
                disabled={!confirmChecked || loading}
                className={styles.btnSuccess}
              >
                {loading ? 'Commiteando...' : 'Commit'}
              </button>
            </div>
          </>
        )}

        {result?.ok === true && (
          <>
            <div className={styles.alertSuccess} style={{ marginBottom: '16px', padding: '12px', borderRadius: '3px' }}>
              <strong>✅ Commit exitoso</strong>
              <pre style={{ margin: '8px 0 0 0', fontSize: '12px', whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(result.data, null, 2)}
              </pre>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={onClose} style={{ padding: '8px 16px' }}>
                Cerrar
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
