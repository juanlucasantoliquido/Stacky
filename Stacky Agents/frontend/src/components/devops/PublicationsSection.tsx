/**
 * PublicationsSection (Plan 88 F5)
 *
 * Flujo preset → materializar → preview YAML → commit HITL → trigger HITL.
 * Montada como sección DECLARATIVA del plan 87 v3 (gate en el shell — C14):
 * esta sección NO renderiza ningún aviso de flag propio, eso lo hace
 * DevOpsPage con FlagGateBanner según healthKey/gateFlagKey/gateMessage.
 */
import React, { useEffect, useState } from 'react';
import { useWorkbench } from '../../store/workbench';
import { api } from '../../api/client';
import { DevOps } from '../../api/endpoints';
import {
  emptyPreset,
  upsertPreset,
  removePreset,
  validatePresetLocal,
  mergeKeysIntoProfile,
  resolvePreview,
  presetsEqual,
  draftNameForPreset,
  type PublicationPreset,
  type PublishGroup,
} from '../../devops/presetsModel';
import { fromParsedSpec, toSpecDict, type PipelineSpecDraft } from '../../devops/specBuilder';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import { PipelineYamlPreview } from './PipelineYamlPreview';
import { CommitPipelineModal } from './CommitPipelineModal';
import { TriggerPipelineSection } from './TriggerPipelineSection';
import { ProductionFlow } from './ProductionFlow';
import { SectionDoctorButton } from './SectionDoctorButton';
import { PreflightPanel } from './PreflightPanel';
import styles from './devops.module.css';

export interface PublicationsSectionProps {
  ctx: DevOpsSectionContext;
}

const DEFAULT_TEMPLATES: Record<string, string> = {
  entry: 'echo "[stacky] publicar {process_name} (entry)"',
  processing: 'echo "[stacky] publicar {process_name} (processing)"',
  output: 'echo "[stacky] publicar {process_name} (output)"',
  default: 'echo "[stacky] publicar {process_name}"',
};

interface CatalogEntry {
  name?: string;
  kind?: string;
  publish_group?: string;
}

interface MaterializeResult {
  spec: object;
  resolved: string[];
  unknown_processes: string[];
}

export const PublicationsSection: React.FC<PublicationsSectionProps> = ({ ctx }) => {
  const activeProjectObj = useWorkbench((s) => s.activeProject);
  const activeProject = activeProjectObj?.name ?? '';

  const [presets, setPresets] = useState<PublicationPreset[]>([]);
  const [loadedPresets, setLoadedPresets] = useState<PublicationPreset[]>([]);
  const [settings, setSettings] = useState<{ step_templates?: Record<string, string> }>({});
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [drafts, setDrafts] = useState<Array<{ name: string; spec: PipelineSpecDraft; updated_at: string }>>([]);
  const [selectedName, setSelectedName] = useState<string>('');
  const [editing, setEditing] = useState<PublicationPreset>(emptyPreset());
  const [actionError, setActionError] = useState<string | null>(null);
  const [materializeResult, setMaterializeResult] = useState<MaterializeResult | null>(null);
  const [materializedDraft, setMaterializedDraft] = useState<PipelineSpecDraft | null>(null);
  const [savedDraftHint, setSavedDraftHint] = useState<string | null>(null);
  const [showCommitModal, setShowCommitModal] = useState(false);
  // Plan 95 F4 — branch del último commit exitoso (trigger + ProductionFlow)
  const [lastCommitBranch, setLastCommitBranch] = useState('');

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
      const loaded = (profile.devops_publication_presets as PublicationPreset[]) ?? [];
      setPresets(loaded);
      setLoadedPresets(loaded);
      setSettings((profile.devops_publication_settings as { step_templates?: Record<string, string> }) ?? {});
      setCatalog((profile.process_catalog as CatalogEntry[]) ?? []);
      setDrafts((profile.devops_pipeline_drafts as Array<{ name: string; spec: PipelineSpecDraft; updated_at: string }>) ?? []);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudo cargar la configuración: ${msg}`);
    }
  };

  const savePresets = async (nextPresets: PublicationPreset[]) => {
    if (!activeProject) return;
    try {
      setActionError(null);
      // C2 — riel GET → merge → PUT OBLIGATORIO.
      const json = await api.get<{ profile?: Record<string, unknown> }>(`/api/projects/${activeProject}/client-profile`);
      const base = json.profile ?? {};
      const merged = mergeKeysIntoProfile(base, { devops_publication_presets: nextPresets });
      await api.put(`/api/projects/${activeProject}/client-profile`, { profile: merged });
      setPresets(nextPresets);
      setLoadedPresets(nextPresets);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudo guardar el preset: ${msg}`);
    }
  };

  const saveSettings = async (nextSettings: { step_templates?: Record<string, string> }) => {
    if (!activeProject) return;
    try {
      setActionError(null);
      const json = await api.get<{ profile?: Record<string, unknown> }>(`/api/projects/${activeProject}/client-profile`);
      const base = json.profile ?? {};
      const merged = mergeKeysIntoProfile(base, { devops_publication_settings: nextSettings });
      await api.put(`/api/projects/${activeProject}/client-profile`, { profile: merged });
      setSettings(nextSettings);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudieron guardar las plantillas: ${msg}`);
    }
  };

  const handleCreateTodoPreset = async () => {
    const todoPreset: PublicationPreset = { name: 'todo-completo', mode: 'todo', groups: [], target: 'gitlab' };
    await savePresets(upsertPreset(presets, todoPreset));
    setSelectedName('todo-completo');
    setEditing(todoPreset);
  };

  const handleSelectPreset = (name: string) => {
    setSelectedName(name);
    const found = presets.find((p) => p.name === name);
    setEditing(found ?? emptyPreset());
    setMaterializeResult(null);
    setMaterializedDraft(null);
    setSavedDraftHint(null);
  };

  const handleSaveEditing = async () => {
    const errors = validatePresetLocal(editing);
    if (errors.length > 0) {
      setActionError(`No se pudo guardar el preset: ${errors.join(' ')}`);
      return;
    }
    await savePresets(upsertPreset(presets, editing));
    setSelectedName(editing.name);
  };

  const handleRemovePreset = async (name: string) => {
    await savePresets(removePreset(presets, name));
    if (selectedName === name) {
      setSelectedName('');
      setEditing(emptyPreset());
    }
  };

  const handleMaterialize = async () => {
    if (!activeProject || !editing.name) return;
    try {
      setActionError(null);
      const result = await DevOps.materializePublication(activeProject, editing.name);
      setMaterializeResult(result);
      setMaterializedDraft(fromParsedSpec(result.spec));
      setSavedDraftHint(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      if (msg.includes('preset_not_found')) {
        setActionError('El preset ya no existe — recargá la lista.');
      } else {
        setActionError(`No se pudo materializar: ${msg}`);
      }
    }
  };

  const handleSaveAsDraft = async () => {
    if (!activeProject || !materializedDraft) return;
    try {
      setActionError(null);
      const json = await api.get<{ profile?: Record<string, unknown> }>(`/api/projects/${activeProject}/client-profile`);
      const base = json.profile ?? {};
      const baseDrafts = (base.devops_pipeline_drafts as Array<{ name: string; spec: PipelineSpecDraft; updated_at: string }>) ?? [];
      const name = draftNameForPreset(baseDrafts.map((d) => d.name), editing.name);
      const nextDrafts = [
        ...baseDrafts,
        { name, spec: toSpecDict(materializedDraft), updated_at: new Date().toISOString() },
      ];
      const merged = mergeKeysIntoProfile(base, { devops_pipeline_drafts: nextDrafts });
      await api.put(`/api/projects/${activeProject}/client-profile`, { profile: merged });
      setDrafts(nextDrafts as Array<{ name: string; spec: PipelineSpecDraft; updated_at: string }>);
      setSavedDraftHint(`Borrador '${name}' guardado — abrilo en la sección Pipelines para editarlo bloque a bloque.`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudo guardar como borrador: ${msg}`);
    }
  };

  const toggleGroup = (group: PublishGroup) => {
    const groups = editing.groups.includes(group)
      ? editing.groups.filter((g) => g !== group)
      : [...editing.groups, group];
    setEditing({ ...editing, groups });
  };

  const toggleProcessName = (name: string) => {
    const processNames = editing.process_names ?? [];
    const next = processNames.includes(name)
      ? processNames.filter((n) => n !== name)
      : [...processNames, name];
    setEditing({ ...editing, process_names: next });
  };

  const catalogEmpty = catalog.length === 0;
  const preview = resolvePreview(editing, catalog);
  const hasUnsaved = !presetsEqual(presets, loadedPresets);

  return (
    <div style={{ display: 'flex', gap: '16px', height: '100%' }}>
      {/* Izquierda: lista + editor de presets */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
        {catalogEmpty && (
          <div className={styles.alertWarning} style={{ marginBottom: '12px' }}>
            El catálogo de procesos está vacío — cargalo en Configuración → Perfil del cliente (sección Catálogo de procesos).
          </div>
        )}

        {hasUnsaved && (
          <div className={styles.textWarn} style={{ marginBottom: '8px', fontSize: '0.9em' }}>Sin guardar</div>
        )}

        {presets.length === 0 ? (
          <div className={styles.emptyState}>
            <p className={styles.textMuted} style={{ marginBottom: '16px' }}>Todavía no hay presets de publicación</p>
            <button
              onClick={() => void handleCreateTodoPreset()}
              className={styles.btnSuccess}
              style={{ padding: '10px 20px' }}
            >
              Crear preset TODO
            </button>
          </div>
        ) : (
          <div style={{ marginBottom: '16px', display: 'flex', gap: '8px', alignItems: 'center' }}>
            <select
              value={selectedName}
              onChange={(e) => handleSelectPreset(e.target.value)}
              style={{ flex: 1, padding: '8px' }}
            >
              <option value="">Nuevo preset...</option>
              {presets.map((p) => (
                <option key={p.name} value={p.name}>{p.name}</option>
              ))}
            </select>
            {selectedName && (
              <button onClick={() => void handleRemovePreset(selectedName)} style={{ padding: '8px' }}>
                Eliminar
              </button>
            )}
            <button onClick={() => void handleCreateTodoPreset()} style={{ padding: '8px' }}>
              Crear preset TODO
            </button>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
          <input
            type="text"
            value={editing.name}
            onChange={(e) => setEditing({ ...editing, name: e.target.value })}
            placeholder="Nombre del preset"
            style={{ padding: '8px' }}
          />
          <div>
            <label style={{ marginRight: '12px' }}>
              <input
                type="radio"
                checked={editing.mode === 'selection'}
                onChange={() => setEditing({ ...editing, mode: 'selection' })}
              />{' '}
              Selección
            </label>
            <label>
              <input
                type="radio"
                checked={editing.mode === 'todo'}
                onChange={() => setEditing({ ...editing, mode: 'todo' })}
              />{' '}
              Todo el catálogo
            </label>
          </div>

          {editing.mode === 'selection' && (
            <div className={styles.panel} style={{ padding: '8px' }}>
              {catalog.map((entry) => (
                <label key={entry.name} style={{ display: 'block' }}>
                  <input
                    type="checkbox"
                    checked={(editing.process_names ?? []).includes(entry.name ?? '')}
                    onChange={() => toggleProcessName(entry.name ?? '')}
                  />{' '}
                  {entry.name} {entry.publish_group && <span style={{ opacity: 0.6 }}>[{entry.publish_group}]</span>}
                </label>
              ))}
            </div>
          )}

          <div>
            <label style={{ marginRight: '12px' }}>
              <input type="checkbox" checked={editing.groups.includes('batch')} onChange={() => toggleGroup('batch')} /> batch
            </label>
            <label>
              <input type="checkbox" checked={editing.groups.includes('agenda')} onChange={() => toggleGroup('agenda')} /> agenda
            </label>
          </div>

          <select
            value={editing.target ?? 'gitlab'}
            onChange={(e) => setEditing({ ...editing, target: e.target.value as 'ado' | 'gitlab' })}
            style={{ padding: '8px' }}
          >
            <option value="gitlab">GitLab</option>
            <option value="ado">Azure DevOps</option>
          </select>

          <button onClick={() => void handleSaveEditing()} className={styles.btnPrimary} style={{ padding: '8px' }}>
            Guardar preset
          </button>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <h4>Plantillas de script (por tipo)</h4>
          {(['entry', 'processing', 'output', 'default'] as const).map((kind) => (
            <div key={kind} style={{ marginBottom: '6px' }}>
              <label style={{ display: 'block', fontSize: '0.85em', opacity: 0.8 }}>{kind}</label>
              <textarea
                value={settings.step_templates?.[kind] ?? ''}
                placeholder={DEFAULT_TEMPLATES[kind]}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    step_templates: { ...settings.step_templates, [kind]: e.target.value },
                  })
                }
                style={{ width: '100%', minHeight: '40px', fontFamily: 'monospace', fontSize: '12px' }}
              />
            </div>
          ))}
          <p style={{ fontSize: '0.8em', opacity: 0.7 }}>Usá {'{process_name}'} para insertar el nombre del proceso.</p>
          <button onClick={() => void saveSettings(settings)} style={{ padding: '8px' }}>
            Guardar plantillas
          </button>
        </div>

        {actionError && (
          <div className={styles.alertError}>
            No se pudo completar la acción: {actionError}
          </div>
        )}
      </div>

      {/* Derecha: preview de resolución + materializar + preview YAML + commit/trigger */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
        <h4>Vista previa de resolución</h4>
        <p>Resueltos: {preview.resolved.join(', ') || '(ninguno)'}</p>
        {preview.excluded.length > 0 && <p style={{ opacity: 0.6 }}>Excluidos por grupo: {preview.excluded.join(', ')}</p>}
        {preview.unknown.length > 0 && (
          <p className={styles.textWarn}>Procesos desconocidos: {preview.unknown.join(', ')}</p>
        )}

        <button
          onClick={() => void handleMaterialize()}
          disabled={catalogEmpty || !editing.name}
          title={catalogEmpty ? 'El catálogo de procesos está vacío' : undefined}
          className={styles.btnSuccess}
          style={{ padding: '10px 20px', marginBottom: '16px' }}
        >
          Materializar
        </button>

        {materializeResult && materializedDraft && (
          <>
            {materializeResult.unknown_processes.length > 0 && (
              <p className={styles.textWarn}>
                Procesos no encontrados en el catálogo: {materializeResult.unknown_processes.join(', ')}
              </p>
            )}
            <PipelineYamlPreview
              spec={materializedDraft}
              ctx={{ health: { flag_enabled: true, generator_enabled: true, trigger_enabled: false, publications_enabled: true }, refetchHealth: () => {} }}
              localErrors={[]}
            />

            {/* Plan 93 — preflight "¿Va a funcionar?" reusado (solo-lectura, informativo) */}
            <PreflightPanel
              ctx={ctx}
              spec={toSpecDict(materializedDraft)}
              project={activeProject ?? ''}
            />

            <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
              <button
                onClick={() => setShowCommitModal(true)}
                className={styles.btnSuccess}
                style={{ padding: '10px 20px' }}
              >
                Commit al repo…
              </button>
              <button onClick={() => void handleSaveAsDraft()} style={{ padding: '10px 20px' }}>
                Guardar como borrador
              </button>
            </div>
            {savedDraftHint && <p className={styles.textSuccess}>{savedDraftHint}</p>}

            <TriggerPipelineSection ctx={ctx} project={activeProject ?? ''} lastBranch={lastCommitBranch} />

            {/* Plan 95 F4 — flujo "Llevar a producción", visible SOLO tras un commit exitoso */}
            {lastCommitBranch && (
              <ProductionFlow ctx={ctx} project={activeProject ?? ''} sourceBranch={lastCommitBranch} />
            )}

            {showCommitModal && (
              <CommitPipelineModal
                spec={materializedDraft}
                project={activeProject ?? ''}
                onSuccess={(branch) => {
                  setLastCommitBranch(branch);
                  setShowCommitModal(false);
                }}
                onClose={() => setShowCommitModal(false)}
                adoCommitSupported={ctx.health.ado_commit_supported === true}
              />
            )}
          </>
        )}

        {/* Plan 104 F3 — Doctor IA de la sección. F3 es AUTOCONTENIDO (deriva el gate acá). */}
        {(() => {
          const doctorFlagOff = ctx?.health?.section_doctor_enabled === false;
          return (
            <SectionDoctorButton
              sectionId="publications"
              project={activeProject ?? ''}
              buildPayload={() => ({ publications: { presets, editing } })}
              gateMessage={doctorFlagOff ? 'El doctor de secciones está apagado (activá la flag en el panel Arnés).' : undefined}
            />
          );
        })()}
      </div>
    </div>
  );
};
