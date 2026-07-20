/**
 * ProductionFlow (Plan 95 F4)
 *
 * Flujo "Llevar a producción": crear MR/PR post-commit, ver su pipeline en
 * vivo y mergear con confirmación HITL (checkbox literal + confirm
 * server-side). Se monta DESPUÉS de un commit exitoso en la sesión
 * (sourceBranch = branch del último commit).
 *
 * Gate inline (no es una sección de DEVOPS_SECTIONS: es sub-feature del
 * builder/publicaciones, §3.12): si production_enabled !== true, FlagGateBanner.
 */
import React, { useEffect, useRef, useState } from 'react';
import { DevOpsProduction, type MrInfo } from '../../api/endpoints';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import { FlagGateBanner } from './FlagGateBanner';
import { TriggerPipelineSection } from './TriggerPipelineSection';
import { mergeButtonEnabled, pipelineStatusLabel, shouldContinuePolling } from '../../devops/productionModel';
import { useConfirm } from '../ui';
import styles from './devops.module.css';

export interface ProductionFlowProps {
  ctx: DevOpsSectionContext;
  project: string;
  sourceBranch: string;
}

/** Espejo de parseVariablesError (VariablesSection.tsx): api/client.ts lanza
 * un Error PLANO (`${status} ${statusText}: ${rawBody}`), sin `.kind`. */
function parseProductionError(e: unknown): { kind: string | null; message: string } {
  const fallback = e instanceof Error ? e.message : 'Error de red';
  if (!(e instanceof Error)) return { kind: null, message: fallback };
  const idx = e.message.indexOf(': ');
  const rawBody = idx >= 0 ? e.message.slice(idx + 2) : '';
  try {
    const parsed = JSON.parse(rawBody);
    return {
      kind: typeof parsed?.kind === 'string' ? parsed.kind : null,
      message: typeof parsed?.error === 'string' ? parsed.error : fallback,
    };
  } catch {
    return { kind: null, message: fallback };
  }
}

export const ProductionFlow: React.FC<ProductionFlowProps> = ({ ctx, project, sourceBranch }) => {
  const askConfirm = useConfirm();
  const [mr, setMr] = useState<MrInfo | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsAdoDefinition, setNeedsAdoDefinition] = useState(false);
  const [mergeConfirmed, setMergeConfirmed] = useState(false);
  const [merging, setMerging] = useState(false);
  // Plan 95 [ADICIÓN ARQUITECTO] Paso 4 — rama destino, para ofrecerla como
  // default editable del trigger post-merge (reusa TriggerPipelineSection).
  const [targetBranch, setTargetBranch] = useState('');
  const pollCountRef = useRef(0);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  if (ctx.health.production_enabled !== true) {
    return (
      <FlagGateBanner
        flagKey="STACKY_DEVOPS_PRODUCTION_ENABLED"
        flagLabel="Llevar a producción"
        message='El flujo "Llevar a producción" (crear MR/PR y mergear) necesita su flag (Configuración → Arnés, categoría DevOps).'
        onEnabled={ctx.refetchHealth}
      />
    );
  }

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  const pollOnce = async (mrId: string) => {
    try {
      const fresh = await DevOpsProduction.getMr(project, mrId);
      setMr(fresh);
      pollCountRef.current += 1;
      if (shouldContinuePolling(pollCountRef.current, fresh.state, document.hidden)) {
        pollTimerRef.current = setTimeout(() => void pollOnce(mrId), 5000);
      }
    } catch (e: unknown) {
      setError(parseProductionError(e).message);
    }
  };

  useEffect(() => stopPolling, []);

  const handleCreateMr = async () => {
    if (!(await askConfirm({ title: 'Crear MR/PR', message: '¿Crear el Merge Request / Pull Request hacia la rama principal?', confirmLabel: 'Crear' }))) return;
    setCreating(true);
    setError(null);
    setNeedsAdoDefinition(false);
    try {
      const created = await DevOpsProduction.createMr({
        project,
        source_branch: sourceBranch,
        ...(targetBranch.trim() ? { target_branch: targetBranch.trim() } : {}),
        confirm: true,
      });
      setMr(created);
      pollCountRef.current = 0;
      pollTimerRef.current = setTimeout(() => void pollOnce(created.id), 5000);
    } catch (e: unknown) {
      const { kind, message } = parseProductionError(e);
      setError(message);
      if (kind === 'ado_definition_missing') setNeedsAdoDefinition(true);
    } finally {
      setCreating(false);
    }
  };

  const handleEnsureDefinition = async () => {
    if (!(await askConfirm({ title: 'Crear pipeline definition', message: '¿Crear la pipeline definition en ADO?', confirmLabel: 'Crear' }))) return;
    setError(null);
    try {
      await DevOpsProduction.ensureAdoDefinition(project);
      setNeedsAdoDefinition(false);
    } catch (e: unknown) {
      setError(parseProductionError(e).message);
    }
  };

  const handleMerge = async () => {
    if (!mr || !mergeConfirmed) return;
    setMerging(true);
    setError(null);
    try {
      const merged = await DevOpsProduction.mergeMr(project, mr.id);
      setMr({ ...mr, state: merged.state });
      stopPolling();
    } catch (e: unknown) {
      setError(parseProductionError(e).message);
    } finally {
      setMerging(false);
    }
  };

  return (
    <div className={styles.panel} style={{ marginTop: '16px' }}>
      <h4 style={{ marginTop: 0 }}>Llevar a producción</h4>

      {error && <div className={styles.alertError}>{error}</div>}

      {needsAdoDefinition && (
        <div className={styles.alertWarning}>
          ADO todavía no tiene la pipeline definition.{' '}
          <button onClick={() => void handleEnsureDefinition()} style={{ padding: '4px 10px' }}>
            Crear la definición del pipeline en ADO
          </button>
        </div>
      )}

      {!mr && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'flex-start' }}>
          <input
            type="text"
            value={targetBranch}
            onChange={(e) => setTargetBranch(e.target.value)}
            placeholder="rama destino (vacío = rama principal del repo)"
            style={{ padding: '8px', width: '320px' }}
          />
          <button onClick={() => void handleCreateMr()} disabled={creating || !sourceBranch} className={styles.btnSuccess}>
            {creating ? 'Creando…' : 'Crear Merge Request / Pull Request'}
          </button>
        </div>
      )}

      {mr && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <p>
            <a href={mr.web_url} target="_blank" rel="noreferrer">
              {mr.web_url}
            </a>{' '}
            — estado: <strong>{mr.state}</strong> — pipeline: {pipelineStatusLabel(mr.pipeline_status)}
            {' '}
            <button onClick={() => void pollOnce(mr.id)} style={{ padding: '2px 8px' }}>
              Actualizar
            </button>
          </p>

          {mr.state === 'open' && (
            <div className={styles.panelMuted} style={{ padding: '12px' }}>
              <label style={{ display: 'flex', alignItems: 'start', gap: '8px' }}>
                <input
                  type="checkbox"
                  checked={mergeConfirmed}
                  onChange={(e) => setMergeConfirmed(e.target.checked)}
                />
                <span>Confirmo el merge a la rama principal</span>
              </label>
              <button
                onClick={() => void handleMerge()}
                disabled={!mergeButtonEnabled(mr) || !mergeConfirmed || merging}
                className={styles.btnSuccess}
                style={{ marginTop: '8px' }}
              >
                {merging ? 'Mergeando…' : 'Mergear'}
              </button>
            </div>
          )}

          {mr.state === 'merged' && (
            <>
              <div className={styles.alertSuccess}>🎉 Mergeado: el pipeline del proyecto quedó actualizado</div>
              {/* Paso 4 (opcional) — reusa TriggerPipelineSection existente (cero backend nuevo) */}
              {ctx.health.trigger_enabled && (
                <div style={{ marginTop: '8px' }}>
                  <p className={styles.textMuted} style={{ marginBottom: '4px' }}>
                    Opcional: correr el pipeline en la rama principal.
                  </p>
                  <TriggerPipelineSection ctx={ctx} project={project} lastBranch={targetBranch} />
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
};
