/**
 * EnvironmentsSection (Plan 89 F5)
 *
 * Wizard de 3 pasos: Configuración → Carpetas (plan-then-apply) → Publicación
 * inicial. Montada como sección DECLARATIVA del plan 87 v3 (gate en el shell
 * — C17): esta sección NO renderiza ningún aviso de SU flag propio, eso lo
 * hace DevOpsPage con FlagGateBanner según healthKey/gateFlagKey/gateMessage.
 * El Paso 2 SÍ gatea su propia dependencia (publications_enabled) con
 * FlagGateBanner, igual que generator/trigger en el 87.
 *
 * CERO lógica nueva de publicación: el Paso 2 compone EXACTAMENTE los
 * componentes del plan 88 (materialize + preview + commit + trigger).
 */
import React, { useEffect, useState } from 'react';
import { useWorkbench } from '../../store/workbench';
import { api } from '../../api/client';
import { DevOps } from '../../api/endpoints';
import {
  mergeKeysIntoProfile,
  upsertPreset,
  emptyPreset,
  type PublicationPreset,
} from '../../devops/presetsModel';
import { fromParsedSpec, type PipelineSpecDraft } from '../../devops/specBuilder';
import { SectionDoctorButton } from './SectionDoctorButton';
import {
  emptyEnvironmentSettings,
  validateSettingsLocal,
  summarizePlan,
  selectablePaths,
  allExistsOk,
  type EnvironmentSettings,
  type FolderKind,
  type PlanEntry,
  type EnvironmentApplyResponse,
} from '../../devops/environmentModel';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import { FlagGateBanner } from './FlagGateBanner';
import { PipelineYamlPreview } from './PipelineYamlPreview';
import { CommitPipelineModal } from './CommitPipelineModal';
import { TriggerPipelineSection } from './TriggerPipelineSection';
import styles from './devops.module.css';

export interface EnvironmentsSectionProps {
  ctx: DevOpsSectionContext;
}

const KINDS: FolderKind[] = ['entry', 'processing', 'output', 'default'];

interface MaterializeResult {
  spec: object;
  resolved: string[];
  unknown_processes: string[];
}

export const EnvironmentsSection: React.FC<EnvironmentsSectionProps> = ({ ctx }) => {
  const activeProjectObj = useWorkbench((s) => s.activeProject);
  const activeProject = activeProjectObj?.name ?? '';

  const [settings, setSettings] = useState<EnvironmentSettings>(emptyEnvironmentSettings());
  const [hasSavedSettings, setHasSavedSettings] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [entries, setEntries] = useState<PlanEntry[]>([]);
  const [rootExists, setRootExists] = useState<boolean | null>(null);
  const [fingerprint, setFingerprint] = useState<string>('');
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [applyResult, setApplyResult] = useState<EnvironmentApplyResponse | null>(null);
  const [verified, setVerified] = useState<boolean | null>(null);
  const [pendingEntries, setPendingEntries] = useState<PlanEntry[]>([]);

  const [presets, setPresets] = useState<PublicationPreset[]>([]);
  const [selectedPresetName, setSelectedPresetName] = useState<string>('');
  const [materializeResult, setMaterializeResult] = useState<MaterializeResult | null>(null);
  const [materializedDraft, setMaterializedDraft] = useState<PipelineSpecDraft | null>(null);
  const [showCommitModal, setShowCommitModal] = useState(false);

  useEffect(() => {
    void loadProfile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject]);

  const loadProfile = async () => {
    if (!activeProject) return;
    try {
      setActionError(null);
      const json = await api.get<{ profile?: Record<string, unknown> }>(`/api/projects/${activeProject}/client-profile`);
      const profile = json.profile ?? {};
      const saved = profile.devops_environment_settings as EnvironmentSettings | undefined;
      if (saved) {
        setSettings(saved);
        setHasSavedSettings(true);
      } else {
        setSettings(emptyEnvironmentSettings());
        setHasSavedSettings(false);
      }
      const loadedPresets = (profile.devops_publication_presets as PublicationPreset[]) ?? [];
      setPresets(loadedPresets);
      const firstTodo = loadedPresets.find((p) => p.mode === 'todo');
      if (firstTodo) setSelectedPresetName(firstTodo.name);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudo cargar la configuración: ${msg}`);
    }
  };

  const saveSettings = async (next: EnvironmentSettings) => {
    if (!activeProject) return;
    try {
      setActionError(null);
      // C2 — riel GET → merge → PUT OBLIGATORIO.
      const json = await api.get<{ profile?: Record<string, unknown> }>(`/api/projects/${activeProject}/client-profile`);
      const base = json.profile ?? {};
      const merged = mergeKeysIntoProfile(base, { devops_environment_settings: next });
      await api.put(`/api/projects/${activeProject}/client-profile`, { profile: merged });
      setSettings(next);
      setHasSavedSettings(true);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudo guardar la configuración: ${msg}`);
    }
  };

  const handleUseExampleLayout = () => {
    setSettings(emptyEnvironmentSettings());
  };

  const updateRoot = (root: string) => {
    setSettings({ ...settings, environment_root: root });
  };

  const updateSegments = (kind: FolderKind, raw: string) => {
    const segs = raw.split(',').map((s) => s.trim()).filter(Boolean);
    setSettings({ ...settings, folder_layout: { ...settings.folder_layout, [kind]: segs } });
  };

  const togglePerProcess = () => {
    setSettings({ ...settings, per_process_subfolder: !settings.per_process_subfolder });
  };

  const localErrors = validateSettingsLocal(settings);
  const canCalculatePlan = hasSavedSettings && !!settings.environment_root;

  const handleCalculatePlan = async () => {
    if (!activeProject) return;
    try {
      setActionError(null);
      const resp = await DevOps.environmentPlan(activeProject);
      setEntries(resp.entries);
      setRootExists(resp.root_exists);
      setFingerprint(resp.layout_fingerprint);
      setConfirmChecked(false);
      setApplyResult(null);
      setVerified(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setActionError(`No se pudo calcular el plan: ${msg}`);
    }
  };

  const handleCreateFolders = async () => {
    if (!activeProject) return;
    try {
      setActionError(null);
      const paths = selectablePaths(entries);
      const resp = await DevOps.environmentApply(activeProject, paths, confirmChecked, fingerprint);
      setApplyResult(resp);
      // Verificación automática post-apply (ADICIÓN v3): re-plan + allExistsOk.
      const rePlan = await DevOps.environmentPlan(activeProject);
      setEntries(rePlan.entries);
      setRootExists(rePlan.root_exists);
      setFingerprint(rePlan.layout_fingerprint);
      const ok = allExistsOk(rePlan.entries);
      setVerified(ok);
      setPendingEntries(ok ? [] : rePlan.entries.filter((e) => e.status !== 'exists_ok'));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      if (msg.includes('plan_stale')) {
        setActionError('El catálogo o la configuración cambiaron desde el último plan. Recalculá el plan.');
        setEntries([]);
        setFingerprint('');
      } else {
        setActionError(`No se pudo crear las carpetas: ${msg}`);
      }
    }
  };

  const handleCreateTodoPreset = async () => {
    if (!activeProject) return;
    try {
      setActionError(null);
      const presetTodo: PublicationPreset = { name: 'inicial-todo', mode: 'todo', groups: [], target: 'gitlab' };
      const json = await api.get<{ profile?: Record<string, unknown> }>(`/api/projects/${activeProject}/client-profile`);
      const base = json.profile ?? {};
      const basePresets = (base.devops_publication_presets as PublicationPreset[]) ?? [];
      const nextPresets = upsertPreset(basePresets, presetTodo);
      const merged = mergeKeysIntoProfile(base, { devops_publication_presets: nextPresets });
      await api.put(`/api/projects/${activeProject}/client-profile`, { profile: merged });
      setPresets(nextPresets);
      setSelectedPresetName(presetTodo.name);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudo crear el preset TODO: ${msg}`);
    }
  };

  const handleMaterialize = async () => {
    if (!activeProject || !selectedPresetName) return;
    try {
      setActionError(null);
      const result = await DevOps.materializePublication(activeProject, selectedPresetName);
      setMaterializeResult(result);
      setMaterializedDraft(fromParsedSpec(result.spec));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudo materializar la publicación inicial: ${msg}`);
    }
  };

  const summary = summarizePlan(entries);
  const step0Ready = hasSavedSettings && !!settings.environment_root && localErrors.length === 0;
  const step1Ready = verified === true;
  const publicationsEnabled = ctx.health.publications_enabled === true;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Stepper visual (C18) */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '8px' }}>
        <span className={step0Ready ? styles.textSuccess : styles.textMuted}>
          {step0Ready ? '✓' : '○'} 1. Configuración
        </span>
        <span className={step1Ready ? styles.textSuccess : styles.textMuted}>
          {step1Ready ? '✓' : '○'} 2. Carpetas
        </span>
        <span className={styles.textMuted}>○ 3. Publicación inicial</span>
      </div>

      {actionError && (
        <div className={styles.alertError}>
          No se pudo completar la acción: {actionError}
        </div>
      )}

      {/* Paso 0 — Configuración */}
      <div className={styles.panel}>
        <h4>Paso 1 — Configuración</h4>
        {!hasSavedSettings && (
          <div className={styles.alertWarning} style={{ marginBottom: '8px' }}>
            Configurá la raíz del ambiente para empezar.{' '}
            <button onClick={handleUseExampleLayout} style={{ padding: '4px 8px' }}>Usar layout de ejemplo</button>
          </div>
        )}
        <input
          type="text"
          value={settings.environment_root}
          onChange={(e) => updateRoot(e.target.value)}
          placeholder="C:\\ambientes\\pacifico"
          style={{ width: '100%', padding: '8px', marginBottom: '8px' }}
        />
        {KINDS.map((kind) => (
          <div key={kind} style={{ marginBottom: '6px' }}>
            <label style={{ display: 'block', fontSize: '0.85em', opacity: 0.8 }}>{kind}</label>
            <input
              type="text"
              value={(settings.folder_layout[kind] ?? []).join(', ')}
              onChange={(e) => updateSegments(kind, e.target.value)}
              placeholder="carpeta1, carpeta2"
              style={{ width: '100%', padding: '6px' }}
            />
          </div>
        ))}
        <label style={{ display: 'block', marginTop: '8px' }}>
          <input type="checkbox" checked={settings.per_process_subfolder} onChange={togglePerProcess} />{' '}
          Crear subcarpeta por proceso
        </label>
        {localErrors.length > 0 && (
          <div className={styles.textWarn} style={{ marginTop: '8px' }}>{localErrors.join(' ')}</div>
        )}
        <button
          onClick={() => void saveSettings(settings)}
          className={styles.btnPrimary}
          style={{ marginTop: '8px' }}
        >
          Guardar configuración
        </button>
      </div>

      {/* Paso 1 — Carpetas (plan-then-apply) */}
      <div className={styles.panel}>
        <h4>Paso 2 — Carpetas</h4>
        <button
          onClick={() => void handleCalculatePlan()}
          disabled={!canCalculatePlan}
          title={!canCalculatePlan ? 'Primero guardá la configuración del Paso 1' : undefined}
          className={styles.btnSuccess}
        >
          Calcular plan
        </button>

        {rootExists === false && (
          <div className={styles.alertWarning} style={{ marginTop: '8px' }}>
            La raíz no existe: se creará completa al aplicar. Verificá la ruta.
          </div>
        )}

        {entries.length > 0 && (
          <>
            <table style={{ width: '100%', marginTop: '8px' }}>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.path}>
                    <td>{e.path}</td>
                    <td
                      className={
                        e.status === 'to_create' ? styles.textSuccess :
                        e.status === 'exists_ok' ? styles.textMuted :
                        styles.textDanger
                      }
                    >
                      {e.status}
                      {e.status === 'conflict' && ' — existe un archivo con ese nombre; Stacky NUNCA lo toca'}
                      {e.status === 'unsafe' && ` — ${e.reason}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p>
              to_create: {summary.to_create} / exists_ok: {summary.exists_ok} / conflict: {summary.conflict} / unsafe: {summary.unsafe}
            </p>
            <label style={{ display: 'block', marginBottom: '8px' }}>
              <input type="checkbox" checked={confirmChecked} onChange={(e) => setConfirmChecked(e.target.checked)} />{' '}
              Confirmo crear las {summary.to_create} carpetas nuevas
            </label>
            <button
              onClick={() => void handleCreateFolders()}
              disabled={!confirmChecked}
              className={styles.btnSuccess}
            >
              Crear carpetas
            </button>
          </>
        )}

        {applyResult && verified === true && (
          <div className={styles.alertSuccess} style={{ marginTop: '8px' }}>
            Ambiente verificado: {entries.length} carpetas existentes, 0 pendientes
          </div>
        )}
        {applyResult && verified === false && (
          <div className={styles.alertError} style={{ marginTop: '8px' }}>
            Quedaron pendientes:
            <ul>
              {pendingEntries.map((e) => <li key={e.path}>{e.path} — {e.status}</li>)}
              {applyResult.failed.map((f) => <li key={f.path}>{f.path} — failed: {f.error}</li>)}
            </ul>
          </div>
        )}
        {applyResult && applyResult.ignored_not_in_layout.length > 0 && (
          <div className={styles.textWarn} style={{ marginTop: '8px' }}>
            Ignorados (fuera del layout): {applyResult.ignored_not_in_layout.join(', ')}
          </div>
        )}
      </div>

      {/* Paso 2 — Publicación inicial (TODO) */}
      <div className={styles.panel}>
        <h4>Paso 3 — Publicación inicial</h4>
        {!publicationsEnabled ? (
          <FlagGateBanner
            flagKey="STACKY_DEVOPS_PUBLICATIONS_ENABLED"
            flagLabel="Publicación inicial"
            message="La publicación inicial necesita la sección Publicaciones (flag STACKY_DEVOPS_PUBLICATIONS_ENABLED, plan 88)."
            onEnabled={ctx.refetchHealth}
          />
        ) : (
          <>
            {presets.length === 0 ? (
              <button onClick={() => void handleCreateTodoPreset()} style={{ padding: '8px 16px' }}>
                Crear preset TODO
              </button>
            ) : (
              <select value={selectedPresetName} onChange={(e) => setSelectedPresetName(e.target.value)} style={{ padding: '8px' }}>
                <option value="">Seleccioná un preset...</option>
                {presets.map((p) => (
                  <option key={p.name} value={p.name}>{p.name}</option>
                ))}
              </select>
            )}
            <button
              onClick={() => void handleMaterialize()}
              disabled={!selectedPresetName}
              className={styles.btnSuccess}
              style={{ marginLeft: '8px' }}
            >
              Materializar publicación inicial
            </button>

            {materializeResult && materializedDraft && (
              <>
                {materializeResult.unknown_processes.length > 0 && (
                  <p className={styles.textWarn}>
                    Procesos no encontrados en el catálogo: {materializeResult.unknown_processes.join(', ')}
                  </p>
                )}
                <PipelineYamlPreview spec={materializedDraft} ctx={ctx} localErrors={[]} />
                <button
                  onClick={() => setShowCommitModal(true)}
                  className={styles.btnSuccess}
                  style={{ padding: '10px 20px', marginTop: '8px' }}
                >
                  Commit al repo…
                </button>
                {ctx.health.trigger_enabled === true && (
                  <TriggerPipelineSection ctx={ctx} project={activeProject} lastBranch="" />
                )}
                {showCommitModal && (
                  <CommitPipelineModal
                    spec={materializedDraft}
                    project={activeProject}
                    onSuccess={() => setShowCommitModal(false)}
                    onClose={() => setShowCommitModal(false)}
                  />
                )}
              </>
            )}
          </>
        )}

        {/* Plan 104 F3 — Doctor IA de la sección. F3 es AUTOCONTENIDO (deriva el gate acá). */}
        {(() => {
          const doctorFlagOff = ctx?.health?.section_doctor_enabled === false;
          return (
            <SectionDoctorButton
              sectionId="environments"
              project={activeProject}
              buildPayload={() => ({ environments: settings })}
              gateMessage={doctorFlagOff ? 'El doctor de secciones está apagado (activá la flag en el panel Arnés).' : undefined}
            />
          );
        })()}
      </div>
    </div>
  );
};
