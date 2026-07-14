/**
 * DeploymentsSection.tsx — Plan 120 F7/F8.
 *
 * Sección "Despliegues": una tarjeta por destino (servidores registrados +
 * Local), deploy en 2 clicks + confirmación HITL, rollback 1 click, chips
 * DORA. Contrato §3.12 C20: entra por 1 entrada en DEVOPS_SECTIONS + este
 * componente, cero cambios en DevOpsPage salvo el registro.
 */
import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { DevOpsDeployments, DevOps, type DeployApp, type DeployOverviewApp } from '../../api/endpoints';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import { useWorkbench } from '../../store/workbench';
import {
  buildTargetCards, rollbackChoices, confirmRequirement, waveOrder, formatDora,
  buildPendingPresetHandoff, showCreatePipelineCta, type TargetCard,
} from './deploymentsModel';
import styles from './devops.module.css';

export interface DeploymentsSectionProps {
  ctx: DevOpsSectionContext;
}

const STORAGE_SELECTED_APP = 'stacky.devops.deployments.selectedApp';
const STORAGE_PENDING_PRESET = 'stacky.devops.pendingPreset';

const STATUS_LABEL: Record<string, string> = {
  nunca: 'Nunca desplegado', ok: 'OK', failed: 'Falló', failed_smoke: 'Falló el smoke',
  running: 'Desplegando…', stale: 'Obsoleto', drift: 'Drift', desconocido: 'Desconocido',
};

const STATUS_CLASS: Record<string, string> = {
  ok: styles.textSuccess, failed: styles.textDanger, failed_smoke: styles.textDanger,
  running: styles.textWarn, stale: styles.textMuted, drift: styles.textWarn,
  desconocido: styles.textMuted, nunca: styles.textMuted,
};

export const DeploymentsSection: React.FC<DeploymentsSectionProps> = ({ ctx }) => {
  const qc = useQueryClient();
  const activeProject = useWorkbench((s) => s.activeProject)?.name ?? '';
  const overviewQuery = useQuery({
    queryKey: ['devops-deployments-overview'],
    queryFn: () => DevOpsDeployments.overview(),
    retry: false,
    refetchInterval: 4000,
  });

  const [selectedAppId, setSelectedAppId] = useState<string | null>(
    () => localStorage.getItem(STORAGE_SELECTED_APP),
  );
  const [showNewApp, setShowNewApp] = useState(false);
  const [selectedTargets, setSelectedTargets] = useState<string[]>([]);
  const [planResult, setPlanResult] = useState<Awaited<ReturnType<typeof DevOpsDeployments.plan>> | null>(null);
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [confirmTextInput, setConfirmTextInput] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [rollbackTarget, setRollbackTarget] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const apps: DeployOverviewApp[] = overviewQuery.data?.apps ?? [];
  const app = apps.find((a) => a.id === selectedAppId) ?? apps[0] ?? null;

  const selectApp = (id: string) => {
    setSelectedAppId(id);
    localStorage.setItem(STORAGE_SELECTED_APP, id);
    setSelectedTargets([]);
    setPlanResult(null);
  };

  // Cards a partir del app + registro de servidores (helper puro, F7).
  const overviewState = Object.fromEntries((app?.targets ?? []).map((t) => [t.key, t.last]));
  const appForModel: DeployApp | null = app
    ? {
        id: app.id,
        artifact: app.artifact as DeployApp['artifact'],
        targets: Object.fromEntries(
          app.targets.filter((t) => t.configured).map((t) => [t.key, {
            install_path: '', smoke: { kind: 'none', url: null, command: null },
            pre_switch: null, post_switch: null, protected: t.protected,
          }]),
        ),
      }
    : null;
  const cards: TargetCard[] = appForModel
    ? buildTargetCards(appForModel, (ctx.servers ?? []).map((s) => ({ alias: s.alias, host: s.host })), overviewState)
    : [];

  const toggleTarget = (key: string) => {
    setSelectedTargets((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : waveOrder([...prev, key])));
    setPlanResult(null);
  };

  const handlePlan = async () => {
    if (!app || selectedTargets.length === 0) return;
    setActionError(null);
    try {
      const result = await DevOpsDeployments.plan(app.id, selectedTargets);
      setPlanResult(result);
      setConfirmChecked(false);
      setConfirmTextInput('');
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'error al planificar');
    }
  };

  const protectedSelected = selectedTargets.some((k) => cards.find((c) => c.key === k)?.protected);
  const confirmReq = confirmRequirement({ protected: protectedSelected }, app?.id ?? '');
  const canConfirmExecute = confirmReq.kind === 'text' ? confirmTextInput === app?.id : confirmChecked;

  const handleExecute = async () => {
    if (!app || !canConfirmExecute) return;
    setBusy(true);
    setActionError(null);
    try {
      await DevOpsDeployments.execute(app.id, selectedTargets, true, confirmReq.kind === 'text' ? confirmTextInput : undefined);
      setPlanResult(null);
      setSelectedTargets([]);
      void qc.invalidateQueries({ queryKey: ['devops-deployments-overview'] });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'error al desplegar');
    } finally {
      setBusy(false);
    }
  };

  const historyQuery = useQuery({
    queryKey: ['devops-deployments-history', app?.id, rollbackTarget],
    queryFn: () => DevOpsDeployments.history(app!.id, rollbackTarget ?? undefined, 20),
    enabled: !!app && !!rollbackTarget,
  });

  const handleRollback = async (version: string) => {
    if (!app || !rollbackTarget) return;
    const cfg = cards.find((c) => c.key === rollbackTarget);
    const req = confirmRequirement({ protected: cfg?.protected }, app.id);
    const confirmText = req.kind === 'text' ? window.prompt(`Escribí "${app.id}" para confirmar el rollback`) ?? '' : undefined;
    if (req.kind === 'text' && confirmText !== app.id) return;
    setBusy(true);
    setActionError(null);
    try {
      await DevOpsDeployments.rollback(app.id, rollbackTarget, version, true, confirmText);
      setRollbackTarget(null);
      void qc.invalidateQueries({ queryKey: ['devops-deployments-overview'] });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'error al hacer rollback');
    } finally {
      setBusy(false);
    }
  };

  const doraChips = app ? formatDora(app.metrics) : [];
  const ctaVisible = showCreatePipelineCta(ctx.health);

  const handleCreatePipelineCta = async () => {
    if (!activeProject) return;
    try {
      const { detected } = await DevOps.detectStack(activeProject);
      const handoff = buildPendingPresetHandoff(detected);
      if (handoff) localStorage.setItem(STORAGE_PENDING_PRESET, JSON.stringify(handoff));
      // C7 v2 (F8): setActiveSection es OPCIONAL — con un shell que aún no lo
      // propague (p.ej. Plan 119), degrada sin romper: el preset queda
      // guardado igual y el operador abre la sub-tab a mano.
      if (ctx.setActiveSection) {
        ctx.setActiveSection('pipelines');
      } else {
        setActionError('Preset guardado — abrí la sub-tab Pipelines');
      }
    } catch {
      /* best-effort: si detect-stack falla, no bloquea la sección */
    }
  };

  if (overviewQuery.isLoading) {
    return <div className={styles.panelMuted}>Cargando despliegues…</div>;
  }

  if (apps.length === 0) {
    return (
      <div className={styles.emptyState}>
        <p>Todavía no hay aplicaciones para desplegar.</p>
        <button type="button" className={styles.btnPrimary} onClick={() => setShowNewApp(true)}>
          Nueva aplicación
        </button>
        {ctaVisible && (
          <button type="button" onClick={() => void handleCreatePipelineCta()}>
            Crear pipeline de deploy
          </button>
        )}
        {showNewApp && <NewAppForm onCreated={(id) => { setShowNewApp(false); selectApp(id); void qc.invalidateQueries({ queryKey: ['devops-deployments-overview'] }); }} onCancel={() => setShowNewApp(false)} />}
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        {apps.map((a) => (
          <button
            key={a.id}
            type="button"
            className={a.id === app?.id ? styles.btnPrimary : undefined}
            onClick={() => selectApp(a.id)}
          >
            {a.name || a.id}
          </button>
        ))}
        <button type="button" onClick={() => setShowNewApp((v) => !v)}>+ Nueva aplicación</button>
        {ctaVisible && (
          <button type="button" onClick={() => void handleCreatePipelineCta()}>
            Crear pipeline de deploy
          </button>
        )}
      </div>

      {showNewApp && (
        <NewAppForm
          onCreated={(id) => { setShowNewApp(false); selectApp(id); void qc.invalidateQueries({ queryKey: ['devops-deployments-overview'] }); }}
          onCancel={() => setShowNewApp(false)}
        />
      )}

      {app && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
            {doraChips.map((chip) => (
              <div key={chip.label} className={styles.healthChip}>
                <strong>{chip.value}</strong> {chip.label}
              </div>
            ))}
          </div>

          {actionError && <div className={styles.alertError}>{actionError}</div>}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
            {cards.map((card) => (
              <div key={card.key} className={styles.panelMuted}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <strong>{card.label}</strong>
                  {card.protected && <span title="Destino protegido">🔒</span>}
                </div>
                <div className={STATUS_CLASS[card.status]}>{STATUS_LABEL[card.status]}</div>
                <div className={styles.textMuted}>
                  {card.version ? `${card.version} (${card.deployedAgo})` : 'sin desplegar'}
                </div>
                <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                  <label>
                    <input
                      type="checkbox"
                      checked={selectedTargets.includes(card.key)}
                      onChange={() => toggleTarget(card.key)}
                      disabled={!card.configured}
                    />
                    {' '}Desplegar
                  </label>
                  {card.canRollback && (
                    <button type="button" onClick={() => setRollbackTarget(card.key)}>Rollback</button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {selectedTargets.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <button type="button" className={styles.btnPrimary} onClick={() => void handlePlan()}>
                Desplegar ({selectedTargets.length})
              </button>
            </div>
          )}

          {planResult && (
            <div className={styles.modalOverlay} role="dialog" aria-label="Plan de despliegue">
              <div className={styles.modalBodyWide}>
                <h3>Plan de despliegue — {planResult.version_id}</h3>
                {planResult.targets.map((t) => (
                  <div key={t.target} className={styles.panelMuted}>
                    <strong>{t.target}</strong>
                    {'error' in t ? (
                      <div className={styles.alertError}>{t.error}</div>
                    ) : (
                      <>
                        <ol>
                          {t.steps.map((s) => <li key={s.name}>{s.name}</li>)}
                        </ol>
                        {t.warnings.map((w, i) => (
                          <div key={i} className={styles.alertWarning}>{w.detail}</div>
                        ))}
                      </>
                    )}
                  </div>
                ))}
                {confirmReq.kind === 'checkbox' ? (
                  <label>
                    <input type="checkbox" checked={confirmChecked} onChange={(e) => setConfirmChecked(e.target.checked)} />
                    {' '}Confirmo el despliegue
                  </label>
                ) : (
                  <label>
                    Escribí "{app.id}" para confirmar:
                    <input value={confirmTextInput} onChange={(e) => setConfirmTextInput(e.target.value)} />
                  </label>
                )}
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <button type="button" className={styles.btnSuccess} disabled={!canConfirmExecute || busy} onClick={() => void handleExecute()}>
                    Confirmar
                  </button>
                  <button type="button" onClick={() => setPlanResult(null)}>Cancelar</button>
                </div>
              </div>
            </div>
          )}

          {rollbackTarget && (
            <div className={styles.modalOverlay} role="dialog" aria-label="Rollback">
              <div className={styles.modalBody}>
                <h3>Rollback — {rollbackTarget}</h3>
                {historyQuery.data && (
                  <ul>
                    {rollbackChoices(historyQuery.data.runs, 10).map((c) => (
                      <li key={c.version}>
                        {c.version} ({c.when}){' '}
                        <button type="button" disabled={busy} onClick={() => void handleRollback(c.version)}>
                          Rollback a esta versión
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <button type="button" onClick={() => setRollbackTarget(null)}>Cerrar</button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

const NewAppForm: React.FC<{ onCreated: (id: string) => void; onCancel: () => void }> = ({ onCreated, onCancel }) => {
  const [id, setId] = useState('');
  const [path, setPath] = useState('');
  const [installPath, setInstallPath] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    try {
      const app: DeployApp = {
        id, artifact: { kind: 'folder', path },
        targets: { __local__: { install_path: installPath, smoke: { kind: 'none', url: null, command: null }, pre_switch: null, post_switch: null, protected: false } },
      };
      await DevOpsDeployments.createApp(app);
      onCreated(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'error al crear la app');
    }
  };

  return (
    <div className={styles.panelMuted}>
      {error && <div className={styles.alertError}>{error}</div>}
      <label>Id <input value={id} onChange={(e) => setId(e.target.value)} placeholder="miapp" /></label>
      <label title="Apuntá a la carpeta donde tu pipeline deja el build (p. ej. <repo>\dist o la carpeta de artefactos del job).">
        Carpeta del build <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="C:\build\miapp\out" />
      </label>
      <label>Install path (Local) <input value={installPath} onChange={(e) => setInstallPath(e.target.value)} placeholder="D:\apps\miapp" /></label>
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button type="button" className={styles.btnPrimary} onClick={() => void submit()}>Crear</button>
        <button type="button" onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
};

export default DeploymentsSection;
