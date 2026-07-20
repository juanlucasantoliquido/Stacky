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
  appendStep,
  updateStage,
  updateJob,
  updateStep,
  toSpecDict,
  fromParsedSpec,
  mergeDraftsIntoProfile,
  validateSpecLocal,
  specsEqual,
  removeSpecVariable,
  type PipelineSpecDraft,
  type StageDraft,
  type JobDraft,
  type StepDraft,
} from '../../devops/specBuilder';
import { PIPELINE_PRESETS, type PipelinePreset, type StackId } from '../../devops/pipelinePresets';
import { consumePendingPreset } from './deploymentsModel'; // Plan 120 F8 — puente Despliegues -> Pipelines
import { PIPELINE_STEP_SNIPPETS, SNIPPET_CATEGORIES, STACK_OPTIONS, filterSnippetsByStack, isStackId } from '../../devops/pipelineStepSnippets';
import { PIPELINE_RECIPES, buildRecipeSteps } from '../../devops/pipelineRecipes';
import { splitSpecVariables } from '../../devops/variablesModel';
import { DevOps, DevOpsVariables, LocalLlmApi } from '../../api/endpoints';
import { DevOpsSectionContext } from '../../pages/DevOpsPage';
import { useConfirm, useTextPrompt } from '../ui';
import { BlockTree } from './BlockTree';
import { BlockProperties } from './BlockProperties';
import { PipelineYamlPreview } from './PipelineYamlPreview';
import { PipelineLintPanel } from './PipelineLintPanel';
import { type LintReport } from './pipelineLint';
import { CommitPipelineModal } from './CommitPipelineModal';
import { TriggerPipelineSection } from './TriggerPipelineSection';
import { ProductionFlow } from './ProductionFlow';
import { SectionDoctorButton } from './SectionDoctorButton';
import { PreflightPanel } from './PreflightPanel';
import { summaryLine, type PreflightResult } from '../../devops/preflightModel';
import styles from './devops.module.css';

export interface PipelineBuilderSectionProps {
  ctx: DevOpsSectionContext;
}

export const PipelineBuilderSection: React.FC<PipelineBuilderSectionProps> = ({ ctx }) => {
  const activeProjectObj = useWorkbench((s) => s.activeProject);
  const activeProject = activeProjectObj?.name ?? '';

  // Estado principal del spec en edición
  const askConfirm = useConfirm();
  const askText = useTextPrompt();
  const [spec, setSpec] = useState<PipelineSpecDraft>(emptySpec());
  // Última versión guardada/cargada (para badge "cambios sin guardar", C15)
  const [loadedSnapshot, setLoadedSnapshot] = useState<PipelineSpecDraft>(emptySpec());
  // Borradores disponibles
  const [drafts, setDrafts] = useState<Array<{ name: string; spec: PipelineSpecDraft; updated_at: string }>>([]);
  const [selectedDraftName, setSelectedDraftName] = useState<string>('');
  // Selección en el árbol
  const [selected, setSelected] = useState<{ si?: number; ji?: number; sti?: number } | null>(null);
  // Plan 97 F1-bis — acción prehecha elegida para insertar en el job seleccionado
  const [snippetId, setSnippetId] = useState<string>('');
  // Plan 97 F1-ter — filtro de texto sobre la biblioteca + receta elegida
  const [snippetFilter, setSnippetFilter] = useState<string>('');
  const [recipeId, setRecipeId] = useState<string>('');
  // UI states
  const [showImportModal, setShowImportModal] = useState(false);
  const [importYaml, setImportYaml] = useState('');
  const [importSource, setImportSource] = useState<'ado' | 'gitlab'>('gitlab');
  const [showCommitModal, setShowCommitModal] = useState(false);
  const [lastCommitBranch, setLastCommitBranch] = useState<string>('');
  // Plan 186 F5/F6 — último LintReport (para el modal de commit) + línea a resaltar
  const [lintReport, setLintReport] = useState<LintReport | undefined>(undefined);
  const [lintHighlight, setLintHighlight] = useState<number | undefined>(undefined);
  // Errores (C16)
  const [actionError, setActionError] = useState<string | null>(null);
  // Debounce para auto-refresh preview (C17)
  const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Plan 93 — último resultado de preflight + el spec (serializado) sobre el
  // que se corrió, para saber si quedó desactualizado (badge -> "sin correr").
  const [lastPreflight, setLastPreflight] = useState<{ result: PreflightResult; specJson: string } | null>(null);
  // Plan 94 F4 — modal "Mover a variable segura" (puente builder → caja fuerte)
  const [moveVarModal, setMoveVarModal] = useState<{ key: string; value: string } | null>(null);
  const [moveVarError, setMoveVarError] = useState<string | null>(null);
  const [moveVarHint, setMoveVarHint] = useState<string | null>(null);
  // Plan 106 F5 — botón "Sugerir con IA local" (HITL): null = todavía no se supo
  // si la flag está ON; false = flag OFF (404) → botón oculto; true = disponible.
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);
  const [llmReachable, setLlmReachable] = useState<boolean>(false);
  const [llmSuggesting, setLlmSuggesting] = useState(false);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [llmJustification, setLlmJustification] = useState<string | null>(null);
  // Playground IA local — selector de modelo reusado en "Sugerir con IA local".
  const [llmModels, setLlmModels] = useState<string[]>([]);
  const [llmModel, setLlmModel] = useState<string>('');

  const localErrors = validateSpecLocal(spec);
  const hasUnsavedChanges = !specsEqual(spec, loadedSnapshot);
  // Plan 93 — memoizado: sin llamadas extra al backend, solo comparación local.
  const currentSpecJson = React.useMemo(() => JSON.stringify(toSpecDict(spec)), [spec]);
  const preflightStale = !lastPreflight || lastPreflight.specJson !== currentSpecJson;

  // Cargar borradores al montar
  useEffect(() => {
    loadDrafts();
  }, []);

  // Plan 120 F8 — puente "Despliegues -> Pipelines": si el operador vino del
  // CTA "Crear pipeline de deploy", preseleccionar el preset sugerido por el
  // stack detectado (one-shot: se limpia la key aunque el preset no exista).
  useEffect(() => {
    const pending = consumePendingPreset(localStorage.getItem('stacky.devops.pendingPreset'));
    if (!pending) return;
    localStorage.removeItem('stacky.devops.pendingPreset');
    const preset = PIPELINE_PRESETS.find((p) => p.id === pending.presetId);
    if (preset) {
      setSpec(preset.build());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Plan 106 F5 — health del modelo local: 404 (flag OFF) => botón oculto (KPI-1/KPI-5).
  useEffect(() => {
    let cancelled = false;
    LocalLlmApi.localHealth()
      .then((res) => {
        if (cancelled) return;
        setLlmAvailable(true);
        setLlmReachable(res.reachable === true);
        // Poblar el selector de modelos (best-effort: si falla, se usa el default de la flag).
        LocalLlmApi.localModels()
          .then((m) => {
            if (cancelled) return;
            setLlmModels(m.models ?? []);
            setLlmModel((prev) => prev || m.current || '');
          })
          .catch(() => { /* selector opcional: silencioso */ });
      })
      .catch(() => {
        if (cancelled) return;
        setLlmAvailable(false);
      });
    return () => { cancelled = true; };
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
      const name = await askText({ title: 'Guardar borrador', message: 'Nombre del borrador:', label: 'Nombre', confirmLabel: 'Guardar' });
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
    if (!(await askConfirm({ title: 'Eliminar borrador', message: `¿Eliminar el borrador '${selectedDraftName}'?`, tone: 'danger', confirmLabel: 'Eliminar' }))) return;
    const newDrafts = drafts.filter(d => d.name !== selectedDraftName);
    await saveDraft(newDrafts);
    setSelectedDraftName('');
    setSpec(emptySpec());
    setLoadedSnapshot(emptySpec());
  };

  // Plan 94 F4 — abre el modal con el value pre-cargado desde spec.variables[key]
  const handleOpenMoveToSecureVariable = (key: string) => {
    setMoveVarError(null);
    setMoveVarModal({ key, value: spec.variables[key] ?? '' });
  };

  // Plan 94 F4 — confirma: crea la variable en el tracker y la saca del spec local
  const handleConfirmMoveToSecureVariable = async () => {
    if (!moveVarModal || !activeProject) return;
    if (!(await askConfirm({ title: 'Crear variable segura', message: `¿Crear '${moveVarModal.key}' como variable segura en el tracker?`, confirmLabel: 'Crear' }))) return;
    try {
      setMoveVarError(null);
      await DevOpsVariables.create({
        project: activeProject,
        key: moveVarModal.key,
        value: moveVarModal.value,
        secret: true,
        confirm: true,
      });
      setSpec((prev) => removeSpecVariable(prev, moveVarModal.key));
      setMoveVarHint(
        `'${moveVarModal.key}' movida al tracker: usala igual, $VAR (GitLab) o $(VAR) (ADO). ` +
        `recommitteá el pipeline (botón Commit) para sacar el valor del YAML actual del repo. ` +
        `Ojo: si este YAML ya se commiteó al repo, el valor sigue viviendo en la historia de git — ` +
        `rotá la credencial en el destino y actualizá la variable segura.`,
      );
      setMoveVarModal(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de red';
      setMoveVarError(`No se pudo mover la variable: ${msg}`);
    }
  };

  const handleImportYaml = async () => {
    if (!importYaml.trim()) return;
    // C15 - confirm si hay trabajo en edición
    if (!specsEqual(spec, emptySpec()) && !(await askConfirm({ title: 'Reemplazar pipeline', message: 'Vas a reemplazar el pipeline en edición. ¿Continuar?', confirmLabel: 'Continuar' }))) {
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

  // Plan 97 F1 — aplica un preset completo de pipeline (galería del estado vacío)
  const handleUsePreset = (preset: PipelinePreset) => {
    setSpec(preset.build());
  };

  // Plan 97 F3 — detección opt-in de stack (solo si la flag está ON vía health)
  const [detecting, setDetecting] = useState(false);
  const [detectError, setDetectError] = useState<string | null>(null);
  // Plan 104 F1 — filtro de presets/snippets/recetas por stack (default "all" = comportamiento 97)
  const [stackFilter, setStackFilter] = useState<StackId | "all">('all');

  const handleDetectStack = async () => {
    if (!activeProject) {
      setDetectError('Seleccioná un proyecto activo primero.');
      return;
    }
    setDetecting(true);
    setDetectError(null);
    try {
      const { detected } = await DevOps.detectStack(activeProject);
      // [C5] guard defensivo Plan 104: si el 97 evoluciona y devuelve un stack no
      // listado en STACK_OPTIONS, el filtro NO muta (degrada silencioso).
      if (isStackId(detected)) setStackFilter(detected);
      if (detected) {
        const preset = PIPELINE_PRESETS.find((p) => p.id === detected);
        if (preset) {
          if (!isEmpty && !(await askConfirm({ title: 'Reemplazar pipeline', message: 'Vas a reemplazar el pipeline en edición con el preset detectado. ¿Continuar?', confirmLabel: 'Continuar' }))) {
            return;
          }
          setSpec(preset.build());
          return;
        }
      }
      setDetectError('No pude detectar el stack de tu proyecto. Elegí un preset de la lista.');
    } catch (e) {
      setDetectError(`No se pudo detectar el stack: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setDetecting(false);
    }
  };

  // Plan 97 F1-bis — inserta la acción prehecha elegida en el job seleccionado
  const handleInsertSnippet = () => {
    if (selected?.si == null || selected?.ji == null || !snippetId) return;
    const snip = PIPELINE_STEP_SNIPPETS.find((s) => s.id === snippetId);
    if (!snip) return;
    setSpec((prev) => appendStep(prev, selected.si!, selected.ji!, snip.build()));
  };

  // Plan 97 F1-ter (C5) — el job seleccionado debe existir de verdad en el spec actual
  const jobSelected =
    selected?.si != null && selected?.ji != null &&
    selected.si < spec.stages.length &&
    selected.ji < (spec.stages[selected.si]?.jobs.length ?? 0);

  // Plan 106 F5 — el step seleccionado debe existir de verdad (working_directory/
  // condition/env viven en StepDraft, no en JobDraft).
  const stepSelected =
    jobSelected && selected?.sti != null &&
    selected.sti < (spec.stages[selected.si!]?.jobs[selected.ji!]?.steps.length ?? 0);
  const selectedStep = stepSelected
    ? spec.stages[selected!.si!].jobs[selected!.ji!].steps[selected!.sti!]
    : null;

  // Plan 106 F5 — pide sugerencias al modelo local y PRE-RELLENA solo lo que está
  // vacío (KPI-5, HITL): nunca pisa lo que el operador ya escribió.
  const handleSuggestWithLocalLlm = async () => {
    if (!selectedStep || selected?.si == null || selected?.ji == null || selected?.sti == null) return;
    setLlmSuggesting(true);
    setLlmError(null);
    setLlmJustification(null);
    try {
      const { suggestions } = await LocalLlmApi.suggestPipeline({
        project: activeProject || 'proyecto-sin-nombre',
        stack: stackFilter === 'all' ? 'generic' : stackFilter,
        model: llmModel || undefined,
        spec_partial: {
          step_name: selectedStep.name,
          script: selectedStep.script,
          working_directory: selectedStep.working_directory ?? '',
          condition: selectedStep.condition ?? '',
          environment_variables: selectedStep.env,
        },
      });
      const patch: Partial<StepDraft> = {};
      if (!selectedStep.working_directory && suggestions.working_directory) {
        patch.working_directory = suggestions.working_directory;
      }
      if (!selectedStep.condition && suggestions.condition) {
        patch.condition = suggestions.condition;
      }
      if (suggestions.environment_variables && Object.keys(suggestions.environment_variables).length > 0) {
        const mergedEnv = { ...suggestions.environment_variables, ...selectedStep.env };
        patch.env = mergedEnv;
      }
      if (Object.keys(patch).length > 0) {
        setSpec((prev) => updateStep(prev, selected.si!, selected.ji!, selected.sti!, patch));
      }
      setLlmJustification(suggestions.justification || null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setLlmError(`No se pudo obtener la sugerencia de IA local: ${msg}`);
    } finally {
      setLlmSuggesting(false);
    }
  };

  // Plan 104 F1 — presets/snippets/recetas filtrados por stack (default "all" = 97 intacto)
  const visiblePresets = PIPELINE_PRESETS.filter((p) => stackFilter === 'all' || p.stack === stackFilter);
  const visibleSnippets = filterSnippetsByStack(PIPELINE_STEP_SNIPPETS, stackFilter);
  const visibleRecipes = PIPELINE_RECIPES.filter((r) => stackFilter === 'all' || r.stack === stackFilter || r.stack === 'all');

  // Plan 97 F1-ter (c) — biblioteca filtrada por texto (label+description+category),
  // compuesta sobre visibleSnippets (Plan 104 F1: primero stack, después texto)
  const filteredSnippets = visibleSnippets.filter((s) => {
    const q = snippetFilter.trim().toLowerCase();
    return q === '' || `${s.label} ${s.description} ${s.category}`.toLowerCase().includes(q);
  });

  // Plan 97 F1-ter (b) — inserta todos los pasos de una receta, en orden, en el job seleccionado
  const handleInsertRecipe = () => {
    if (!jobSelected || !recipeId) return;
    const rec = PIPELINE_RECIPES.find((r) => r.id === recipeId);
    if (!rec) return;
    setSpec((prev) => buildRecipeSteps(rec).reduce(
      (acc, st) => appendStep(acc, selected!.si!, selected!.ji!, st), prev));
  };

  // Plan 97 F1-ter (C1) — scaffolda stage+job vacío y lo selecciona, para llegar al
  // inserter de acciones sueltas sin partir de un preset completo
  const handleStartEmptyJob = () => {
    const scaffolded = addJob(addStage(emptySpec()), 0);
    setSpec(scaffolded);
    setSelected({ si: 0, ji: 0 });
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
            <span className={styles.textWarn} style={{ fontSize: '0.9em' }}>Cambios sin guardar</span>
          )}
        </div>

        <div style={{ marginBottom: '16px', display: 'flex', gap: '8px' }}>
          <button onClick={() => setShowImportModal(true)} style={{ padding: '8px' }}>
            Importar YAML
          </button>
        </div>

        {/* Plan 94 F4 — aviso: variables que parecen secretos y quedan EN EL YAML */}
        {moveVarHint && (
          <div className={styles.alertSuccess} style={{ marginBottom: '16px' }}>
            {moveVarHint}
          </div>
        )}
        {ctx.health.variables_enabled === true && splitSpecVariables(spec).secretLooking.length > 0 && (
          <div className={styles.alertWarning} style={{ marginBottom: '16px' }}>
            <p style={{ margin: '0 0 8px 0' }}>
              Estas variables parecen secretos y van a quedar EN EL YAML del repo:{' '}
              {splitSpecVariables(spec).secretLooking.join(', ')}
            </p>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {splitSpecVariables(spec).secretLooking.map((k) => (
                <button key={k} onClick={() => handleOpenMoveToSecureVariable(k)} style={{ padding: '4px 10px' }}>
                  Mover a variable segura: {k}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Plan 104 F1 — selector de stack: filtra presets/snippets/recetas. Default "all" = 97 intacto. */}
        <div style={{ marginBottom: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <label className={styles.textMuted}>Stack:</label>
          <select
            value={stackFilter}
            onChange={(e) => setStackFilter(e.target.value as StackId | 'all')}
            style={{ padding: '4px 8px' }}
          >
            {STACK_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {/* C11 - CTA estado vacío */}
        {isEmpty ? (
          <div className={styles.emptyState}>
            {/* Plan 97 F3 — detección opt-in (solo si la flag está ON vía health) */}
            {ctx.health.stack_detect_enabled && (
              <div style={{ marginBottom: '12px' }}>
                <button
                  onClick={() => void handleDetectStack()}
                  disabled={detecting || !activeProject}
                  className={styles.btnPrimary}
                  style={{ padding: '8px 16px' }}
                >
                  {detecting ? 'Detectando…' : 'Detectar stack de mi proyecto'}
                </button>
                {detectError && <p className={styles.textWarn} style={{ marginTop: '8px' }}>{detectError}</p>}
              </div>
            )}
            {/* Plan 97 F1 — galería de presets por stack (antes del CTA genérico) */}
            <div style={{ marginBottom: '16px' }}>
              <p className={styles.textMuted} style={{ marginBottom: '8px' }}>
                Elegí un preset para tu proyecto:
              </p>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {visiblePresets.map((preset) => (
                  <button
                    key={preset.id}
                    onClick={() => handleUsePreset(preset)}
                    className={styles.btnPrimary}
                    style={{ padding: '10px 16px', textAlign: 'left' }}
                    title={preset.description}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
            <p className={styles.textMuted} style={{ marginBottom: '16px' }}>
              Agregá tu primer stage o importá un YAML existente
            </p>
            <button
              onClick={() => setSpec(starterSpec())}
              className={styles.btnSuccess}
              style={{ padding: '10px 20px' }}
            >
              Empezar con ejemplo
            </button>
            {' '}
            <button
              onClick={() => setSpec(addStage(spec))}
              className={styles.btnPrimary}
              style={{ padding: '10px 20px' }}
            >
              + stage
            </button>
            {' '}
            <button
              onClick={handleStartEmptyJob}
              className={styles.btnPrimary}
              style={{ padding: '10px 20px' }}
              title="Crea un stage y un job vacíos y los selecciona, para insertar acciones prehechas sueltas"
            >
              Insertá acciones sueltas (job vacío)
            </button>
          </div>
        ) : (
          <BlockTree spec={spec} setSpec={setSpec} selected={selected} setSelected={setSelected} />
        )}

        {/* C16 - área de error visible */}
        {actionError && (
          <div className={styles.alertError} style={{ marginTop: '16px' }}>
            {actionError}
          </div>
        )}
      </div>

      {/* Panel derecho: propiedades + preview */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
        <BlockProperties spec={spec} setSpec={setSpec} selected={selected} />

        {/* Plan 97 F1-bis/F1-ter — inserter de acciones prehechas + recetas (solo con un job seleccionado que existe de verdad, C5) */}
        {jobSelected && (
          <div style={{ marginTop: '8px', display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <label className={styles.textMuted}>Insertar acción prehecha:</label>
            <input
              type="text"
              value={snippetFilter}
              onChange={(e) => setSnippetFilter(e.target.value)}
              placeholder="Filtrar acciones…"
              style={{ padding: '4px 8px' }}
            />
            <select value={snippetId} onChange={(e) => setSnippetId(e.target.value)}>
              <option value="">— elegí una acción —</option>
              {SNIPPET_CATEGORIES
                .map((cat) => ({ cat, items: filteredSnippets.filter((s) => s.category === cat) }))
                .filter((g) => g.items.length > 0)
                .map((g) => (
                  <optgroup key={g.cat} label={g.cat}>
                    {g.items.map((s) => (
                      <option key={s.id} value={s.id} title={s.description}>{s.label}</option>
                    ))}
                  </optgroup>
                ))}
            </select>
            <button onClick={handleInsertSnippet} disabled={!snippetId} className={styles.btnPrimary} style={{ padding: '6px 12px' }}>
              Insertar acción
            </button>
            {(() => {
              const s = PIPELINE_STEP_SNIPPETS.find((x) => x.id === snippetId);
              if (!s || (!s.needsEdit && !s.requires)) return null;
              return (
                <p className={styles.textWarn} style={{ margin: 0, width: '100%' }}>
                  {s.needsEdit && '⚠ Editá el valor de ejemplo antes de usar. '}
                  {s.requires && `Requiere '${s.requires}' en el runner.`}
                </p>
              );
            })()}
            <label className={styles.textMuted}>Insertar receta (varios pasos):</label>
            <select value={recipeId} onChange={(e) => setRecipeId(e.target.value)}>
              <option value="">— elegí una receta —</option>
              {visibleRecipes.map((r) => (
                <option key={r.id} value={r.id} title={r.description}>{r.label}</option>
              ))}
            </select>
            <button onClick={handleInsertRecipe} disabled={!recipeId} className={styles.btnPrimary} style={{ padding: '6px 12px' }}>
              Insertar receta
            </button>
          </div>
        )}

        {/* Plan 106 F5 — "Sugerir con IA local": solo si la flag está ON (health no 404)
            y hay un step seleccionado (working_directory/condition/env viven ahí). HITL:
            solo pre-rellena campos vacíos; el operador revisa y edita todo antes de guardar. */}
        {llmAvailable === true && stepSelected && (
          <div style={{ marginTop: '8px', display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            {llmModels.length > 0 && (
              <select
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value)}
                style={{ padding: '4px 8px' }}
                title="Modelo de IA local a usar para la sugerencia"
              >
                {(llmModel && !llmModels.includes(llmModel) ? [llmModel, ...llmModels] : llmModels).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            )}
            <button
              onClick={() => void handleSuggestWithLocalLlm()}
              disabled={llmSuggesting}
              className={styles.btnPrimary}
              style={{ padding: '6px 12px' }}
              title="Pide sugerencias de working directory, condition y variables de entorno a tu modelo de IA local"
            >
              {llmSuggesting ? 'Consultando IA local…' : 'Sugerir con IA local'}
            </button>
            <span className={styles.textMuted} style={{ fontSize: '0.85em' }}>
              IA local: {llmReachable ? 'disponible' : 'sin conexión'}
            </span>
            {llmJustification && (
              <p className={styles.textMuted} style={{ margin: 0, width: '100%', fontSize: '0.9em' }}>
                {llmJustification}
              </p>
            )}
            {llmError && (
              <p className={styles.textWarn} style={{ margin: 0, width: '100%' }}>{llmError}</p>
            )}
          </div>
        )}

        <div style={{ marginTop: '16px' }}>
          <PipelineYamlPreview spec={spec} ctx={ctx} localErrors={localErrors} highlightLine={lintHighlight} />
          {/* Plan 186 F5 — panel de lint (se auto-oculta con la flag OFF/404) */}
          <PipelineLintPanel
            spec={spec}
            project={activeProject ?? ''}
            onHighlightLine={setLintHighlight}
            onReport={setLintReport}
          />
        </div>

        {/* Plan 93 — preflight "¿Va a funcionar?" (solo-lectura, informativo) */}
        <PreflightPanel
          ctx={ctx}
          spec={toSpecDict(spec)}
          project={activeProject ?? ''}
          onResult={(result) => setLastPreflight({ result, specJson: currentSpecJson })}
        />

        <div style={{ marginTop: '16px', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button
            onClick={() => setShowCommitModal(true)}
            disabled={localErrors.length > 0}
            title={localErrors.length > 0 ? 'Resolvé los avisos primero' : undefined}
            className={styles.btnSuccess}
            style={{ padding: '10px 20px' }}
          >
            Commit al repo…
          </button>
          {/* Plan 93 — badge informativo: NUNCA deshabilita ni bloquea (HITL §3.3) */}
          <span className={styles.textMuted} style={{ fontSize: '0.9em' }} title={
            !lastPreflight ? 'Todavía no corriste el preflight' :
            preflightStale ? 'El pipeline cambió desde el último preflight' :
            summaryLine(lastPreflight.result.checks)
          }>
            {!lastPreflight || preflightStale
              ? 'Preflight: – sin correr'
              : `Preflight: ${
                  lastPreflight.result.checks.some((c) => c.status === 'fail') ? '✖ con problemas'
                  : lastPreflight.result.checks.some((c) => c.status === 'warn' || c.status === 'unavailable') ? '⚠ con avisos'
                  : '✔ verde'
                } — ${summaryLine(lastPreflight.result.checks)}`}
          </span>
        </div>

        {ctx.health.trigger_enabled && (
          <TriggerPipelineSection ctx={ctx} project={activeProject ?? ''} lastBranch={lastCommitBranch} />
        )}

        {/* Plan 95 F4 — flujo "Llevar a producción", visible SOLO tras un commit exitoso */}
        {lastCommitBranch && (
          <ProductionFlow ctx={ctx} project={activeProject ?? ''} sourceBranch={lastCommitBranch} />
        )}

        {/* Plan 104 F3 — Doctor IA de la sección. F3 es AUTOCONTENIDO: deriva el
            gate acá mismo (no depende de F5). */}
        {(() => {
          const doctorFlagOff = ctx?.health?.section_doctor_enabled === false;
          return (
            <SectionDoctorButton
              sectionId="pipeline"
              project={activeProject}
              buildPayload={() => ({ spec })}
              gateMessage={doctorFlagOff ? 'El doctor de secciones está apagado (activá la flag en el panel Arnés).' : undefined}
              localDoctorEnabled={ctx.health.local_doctor_enabled === true}
            />
          );
        })()}
      </div>

      {/* Modales */}
      {showImportModal && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalBodyWide}>
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
                className={styles.btnPrimary}
              >
                Importar
              </button>
            </div>
          </div>
        </div>
      )}

      {showCommitModal && (
        <CommitPipelineModal
          spec={spec}
          project={activeProject ?? ''}
          onSuccess={handleCommitSuccess}
          onClose={() => setShowCommitModal(false)}
          adoCommitSupported={ctx.health.ado_commit_supported === true}
          lintReport={lintReport}
        />
      )}

      {/* Plan 94 F4 — modal "Mover a variable segura" */}
      {moveVarModal && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalBodyWide}>
            <h3>Mover a variable segura: {moveVarModal.key}</h3>
            <p className={styles.textMuted}>
              Se va a crear como variable secreta en el tracker y se va a sacar del YAML en edición.
            </p>
            <input
              type="password"
              value={moveVarModal.value}
              onChange={(e) => setMoveVarModal({ ...moveVarModal, value: e.target.value })}
              placeholder="valor"
              style={{ padding: '8px', width: '100%', marginBottom: '10px' }}
            />
            {moveVarError && <p className={styles.textDanger}>{moveVarError}</p>}
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button onClick={() => setMoveVarModal(null)} style={{ padding: '8px 16px' }}>
                Cancelar
              </button>
              <button onClick={() => void handleConfirmMoveToSecureVariable()} className={styles.btnSuccess}>
                Crear variable segura
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
