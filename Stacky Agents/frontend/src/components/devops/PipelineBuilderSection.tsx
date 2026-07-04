/**
 * PipelineBuilderSection (Plan 87 F5)
 * Editor visual de pipelines (stages → jobs → steps)
 *
 * Flujos principales:
 * - Edición gráfica del spec con validación en vivo (C12)
 * - Gestión de borradores (C15, FIX C1)
 * - Preview de YAML ADO/GitLab (C17, C14)
 * - Commit HITL al repo
 * - Trigger/monitor de pipelines (reusa CIPipeline, FIX C5)
 */
import React, { useState, useEffect, useRef } from 'react';
import { useWorkbench } from '../../store/workbench';
import { api } from '../../api/client';
import {
  emptySpec,
  starterSpec,
  addStage,
  removeStage,
  addJob,
  removeJob,
  addStep,
  removeStep,
  updateStage,
  updateJob,
  updateStep,
  toSpecDict,
  fromParsedSpec,
  mergeDraftsIntoProfile,
  validateSpecLocal,
  specsEqual,
  type PipelineSpecDraft,
  type StageDraft,
  type JobDraft,
  type StepDraft,
} from '../../devops/specBuilder';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import { BlockTree } from './BlockTree';
import { BlockProperties } from './BlockProperties';
import { PipelineYamlPreview } from './PipelineYamlPreview';
import { CommitPipelineModal } from './CommitPipelineModal';
import { TriggerPipelineSection } from './TriggerPipelineSection';

export interface PipelineBuilderSectionProps {
  ctx: DevOpsSectionContext;
}

export const PipelineBuilderSection: React.FC<PipelineBuilderSectionProps> = ({ ctx }) => {
  const activeProjectObj = useWorkbench((s) => s.activeProject);
  const activeProject = activeProjectObj?.name ?? '';

  // Estado principal del spec en edición
  const [spec, setSpec] = useState<PipelineSpecDraft>(emptySpec());
  // Última versión guardada/cargada (para badge "cambios sin guardar", C15)
  const [loadedSnapshot, setLoadedSnapshot] = useState<PipelineSpecDraft>(emptySpec());
  // Borradores disponibles
  const [drafts, setDrafts] = useState<Array<{ name: string; spec: PipelineSpecDraft; updated_at: string }>>([]);
  const [selectedDraftName, setSelectedDraftName] = useState<string>('');
  // Selección en el árbol
  const [selected, setSelected] = useState<{ si?: number; ji?: number; sti?: number } | null>(null);
  // UI states
  const [showImportModal, setShowImportModal] = useState(false);
  const [importYaml, setImportYaml] = useState('');
  const [importSource, setImportSource] = useState<'ado' | 'gitlab'>('gitlab');
  const [showCommitModal, setShowCommitModal] = useState(false);
  const [lastCommitBranch, setLastCommitBranch] = useState<string>('');
  // Errores (C16)
  const [actionError, setActionError] = useState<string | null>(null);
  // Debounce para auto-refresh preview (C17)
  const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const localErrors = validateSpecLocal(spec);
  const hasUnsavedChanges = !specsEqual(spec, loadedSnapshot);

  // Cargar borradores al montar
  useEffect(() => {
    loadDrafts();
  }, []);

  // Auto-refresh preview con debounce (C17)
  useEffect(() => {
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current);
    }
    if (ctx.health.generator_enabled && localErrors.length === 0) {
      refreshTimeoutRef.current = setTimeout(() => {
        // El preview se refresca automáticamente en PipelineYamlPreview
      }, 800);
    }
    return () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
    };
  }, [spec, ctx.health.generator_enabled, localErrors.length]);

  const loadDrafts = async () => {
    if (!activeProject) return;
    try {
      setActionError(null);
      const json = await api.get<{ profile?: Record<string, unknown> }>(`/api/projects/${activeProject}/client-profile`);
      const profileDrafts = (json.profile?.devops_pipeline_drafts as Array<{ name: string; spec: PipelineSpecDraft; updated_at: string }>) ?? [];
      setDrafts(profileDrafts);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudieron cargar los borradores: ${msg}`);
    }
  };

  const saveDraft = async (newDrafts: typeof drafts) => {
    if (!activeProject) return;
    try {
      setActionError(null);
      // FIX C1 - riel GET→merge→PUT OBLIGATORIO
      const json = await api.get<{ profile?: Record<string, unknown> }>(`/api/projects/${activeProject}/client-profile`);
      const baseProfile = json.profile ?? {};
      const mergedProfile = mergeDraftsIntoProfile(baseProfile, newDrafts);
      await api.put(`/api/projects/${activeProject}/client-profile`, { profile: mergedProfile });
      setDrafts(newDrafts);
      setLoadedSnapshot(spec); // Actualizar snapshot tras guardar
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudieron guardar los borradores: ${msg}`);
      throw e; // Re-throw para que el caller decida
    }
  };

  const handleSaveDraft = async () => {
    if (!selectedDraftName) {
      // Guardar como nuevo
      const name = prompt('Nombre del borrador:');
      if (!name) return;
      const newDrafts = [
        ...drafts,
        { name, spec: JSON.parse(JSON.stringify(spec)), updated_at: new Date().toISOString() },
      ];
      await saveDraft(newDrafts);
      setSelectedDraftName(name);
    } else {
      // Actualizar existente
      const newDrafts = drafts.map(d =>
        d.name === selectedDraftName
          ? { ...d, spec: JSON.parse(JSON.stringify(spec)), updated_at: new Date().toISOString() }
          : d
      );
      await saveDraft(newDrafts);
    }
  };

  const handleLoadDraft = async (draftName: string) => {
    const draft = drafts.find(d => d.name === draftName);
    if (!draft) return;
    setSpec(draft.spec);
    setLoadedSnapshot(draft.spec);
    setSelectedDraftName(draftName);
    setSelected(null);
    setActionError(null);
  };

  const handleDeleteDraft = async () => {
    if (!selectedDraftName) return;
    // C15 - confirm antes de eliminar
    if (!window.confirm(`¿Eliminar el borrador '${selectedDraftName}'?`)) return;
    const newDrafts = drafts.filter(d => d.name !== selectedDraftName);
    await saveDraft(newDrafts);
    setSelectedDraftName('');
    setSpec(emptySpec());
    setLoadedSnapshot(emptySpec());
  };

  const handleImportYaml = async () => {
    if (!importYaml.trim()) return;
    // C15 - confirm si hay trabajo en edición
    if (!specsEqual(spec, emptySpec()) && !window.confirm('Vas a reemplazar el pipeline en edición. ¿Continuar?')) {
      return;
    }
    try {
      setActionError(null);
      const json = await api.post<{ spec: Record<string, unknown> }>('/api/devops/parse-yaml', {
        source: importSource,
        yaml: importYaml,
      });
      const imported = fromParsedSpec(json.spec);
      setSpec(imported);
      setLoadedSnapshot(imported);
      setShowImportModal(false);
      setImportYaml('');
      setSelectedDraftName('');
      setSelected(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudo importar el YAML: ${msg}`);
    }
  };

  const handleCommitSuccess = (branch: string) => {
    setLastCommitBranch(branch);
    setShowCommitModal(false);
  };

  // C11 - estado vacío
  const isEmpty = spec.stages.length === 0;

  return (
    <div style={{ display: 'flex', gap: '16px', height: '100%' }}>
      {/* Panel izquierdo: árbol de bloques */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
        <div style={{ marginBottom: '16px' }}>
          <input
            type="text"
            value={spec.name}
            onChange={(e) => setSpec({ ...spec, name: e.target.value })}
            placeholder="Nombre del pipeline"
            style={{ width: '100%', padding: '8px', fontSize: '14px' }}
          />
        </div>

        <div style={{ marginBottom: '16px', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <select
            value={selectedDraftName}
            onChange={(e) => e.target.value && handleLoadDraft(e.target.value)}
            style={{ flex: 1, padding: '8px' }}
          >
            <option value="">Nuevo pipeline...</option>
            {drafts.map((d) => (
              <option key={d.name} value={d.name}>
                {d.name}
              </option>
            ))}
          </select>
          {selectedDraftName && (
            <button onClick={() => void handleDeleteDraft()} style={{ padding: '8px' }}>
              Eliminar borrador
            </button>
          )}
          <button onClick={() => void handleSaveDraft()} style={{ padding: '8px' }}>
            Guardar
          </button>
          {hasUnsavedChanges && (
            <span style={{ color: '#ffc107', fontSize: '0.9em' }}>Cambios sin guardar</span>
          )}
        </div>

        <div style={{ marginBottom: '16px', display: 'flex', gap: '8px' }}>
          <button onClick={() => setShowImportModal(true)} style={{ padding: '8px' }}>
            Importar YAML
          </button>
        </div>

        {/* C11 - CTA estado vacío */}
        {isEmpty ? (
          <div style={{ padding: '40px', textAlign: 'center', backgroundColor: '#f8f9fa', borderRadius: '4px' }}>
            <p style={{ marginBottom: '16px', color: '#6c757d' }}>
              Agregá tu primer stage o importá un YAML existente
            </p>
            <button
              onClick={() => setSpec(starterSpec())}
              style={{ padding: '10px 20px', backgroundColor: '#28a745', color: 'white', border: 'none', borderRadius: '4px' }}
            >
              Empezar con ejemplo
            </button>
            {' '}
            <button
              onClick={() => setSpec(addStage(spec))}
              style={{ padding: '10px 20px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '4px' }}
            >
              + stage
            </button>
          </div>
        ) : (
          <BlockTree spec={spec} setSpec={setSpec} selected={selected} setSelected={setSelected} />
        )}

        {/* C16 - área de error visible */}
        {actionError && (
          <div style={{ marginTop: '16px', padding: '12px', backgroundColor: '#f8d7da', border: '1px solid #f5c6cb', borderRadius: '4px', color: '#721c24' }}>
            {actionError}
          </div>
        )}
      </div>

      {/* Panel derecho: propiedades + preview */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
        <BlockProperties spec={spec} setSpec={setSpec} selected={selected} />

        <div style={{ marginTop: '16px' }}>
          <PipelineYamlPreview spec={spec} ctx={ctx} localErrors={localErrors} />
        </div>

        <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
          <button
            onClick={() => setShowCommitModal(true)}
            disabled={localErrors.length > 0}
            title={localErrors.length > 0 ? 'Resolvé los avisos primero' : undefined}
            style={{ padding: '10px 20px', backgroundColor: '#28a745', color: 'white', border: 'none', borderRadius: '4px' }}
          >
            Commit al repo…
          </button>
        </div>

        {ctx.health.trigger_enabled && (
          <TriggerPipelineSection project={activeProject ?? ''} lastBranch={lastCommitBranch} />
        )}
      </div>

      {/* Modales */}
      {showImportModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '4px', width: '600px', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
            <h3>Importar YAML</h3>
            <select
              value={importSource}
              onChange={(e) => setImportSource(e.target.value as 'ado' | 'gitlab')}
              style={{ marginBottom: '10px', padding: '8px', width: '100%' }}
            >
              <option value="ado">Azure DevOps</option>
              <option value="gitlab">GitLab CI</option>
            </select>
            <textarea
              value={importYaml}
              onChange={(e) => setImportYaml(e.target.value)}
              placeholder="Pegá tu YAML acá..."
              style={{ flex: 1, minHeight: '300px', fontFamily: 'monospace', fontSize: '12px', padding: '8px', marginBottom: '10px' }}
            />
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button onClick={() => setShowImportModal(false)} style={{ padding: '8px 16px' }}>
                Cancelar
              </button>
              <button
                onClick={() => void handleImportYaml()}
                disabled={!importYaml.trim()}
                style={{ padding: '8px 16px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '4px' }}
              >
                Importar
              </button>
            </div>
          </div>
        </div>
      )}

      {showCommitModal && (
        <CommitPipelineModal spec={spec} project={activeProject ?? ''} onSuccess={handleCommitSuccess} onClose={() => setShowCommitModal(false)} />
      )}
    </div>
  );
};
