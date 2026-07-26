/**
 * specBuilder.ts - Plan 87 F3
 * Lógica pura del editor de pipelines (stages → jobs → steps)
 * Todas las funciones son INMUTABLES (devuelven copia nueva)
 */

// Tipos espejo del contrato Python (pipeline_spec.py)
// Keys usan snake_case para matchear 1:1 con dict_to_spec
export interface StepDraft {
  name: string;
  script: string;
  working_directory?: string | null;
  condition?: string | null;
  env: Record<string, string>;
}

// Plan 243 F1 — paso `- task: X@N` con `inputs:`. Espejo de pipeline_spec.TaskStep.
// El 100% de los pasos de los pipelines ADO reales del ecosistema se escribe así.
export interface TaskStepDraft {
  name: string;
  task: string;
  inputs: Record<string, string>;
  condition?: string | null;
  env: Record<string, string>;
}

// Plan 243 F1 — job `- deployment:`. Espejo de pipeline_spec.DeploymentJob.
export interface DeploymentJobDraft {
  name: string;
  environment: string;
  strategy: string;
  steps: TaskStepDraft[];
  checkout: boolean;
  download_artifacts: string[];
  display_name?: string | null;
}

export interface JobDraft {
  name: string;
  steps: StepDraft[];
  image?: string | null;
  pool_vm_image?: string | null;
  runner_tags: string[];
  variables: Record<string, string>;
  artifacts: string[];
  services: string[];
  // Plan 243 F1 (aditivo, opcional para no romper drafts del Plan 97)
  task_steps?: TaskStepDraft[];
  pool_name?: string | null;
  depends_on?: string[];
  display_name?: string | null;
}

export interface StageDraft {
  name: string;
  jobs: JobDraft[];
  condition?: string | null;
  // Plan 243 F1 (aditivo)
  deployments?: DeploymentJobDraft[];
  pool_name?: string | null;
  pool_vm_image?: string | null;
  depends_on?: string[];
  display_name?: string | null;
}

export interface PipelineSpecDraft {
  name: string;
  stages: StageDraft[];
  variables: Record<string, string>;
  trigger_branches: string[];
  raw_yaml?: string | null;
  raw_yaml_target?: "ado" | "gitlab" | null;
  // Plan 243 F1 (aditivo)
  trigger_disabled?: boolean;
  trigger_paths?: string[];
  pr_disabled?: boolean;
  pool_vm_image?: string | null;
  pool_name?: string | null;
  root_task_steps?: TaskStepDraft[];
}

// Helpers inmutables de copia profunda
function cloneStage(stage: StageDraft): StageDraft {
  return {
    ...stage,
    jobs: stage.jobs.map((job) => cloneJob(job)),
  };
}

function cloneJob(job: JobDraft): JobDraft {
  return {
    ...job,
    steps: job.steps.map((step) => ({ ...step })),
  };
}

function cloneSpec(spec: PipelineSpecDraft): PipelineSpecDraft {
  return {
    ...spec,
    stages: spec.stages.map((s) => cloneStage(s)),
  };
}

/**
 * Spec vacío (base para empezar)
 */
export function emptySpec(): PipelineSpecDraft {
  return {
    name: "",
    stages: [],
    variables: {},
    trigger_branches: [],
  };
}

/**
 * Ejemplo VÁLIDO y editable para "Empezar con ejemplo" (C11)
 */
export function starterSpec(): PipelineSpecDraft {
  return {
    name: "mi-pipeline",
    stages: [{
      name: "build",
      jobs: [{
        name: "build-job",
        steps: [{
          name: "compilar",
          script: 'echo "reemplazar por el comando real"',
          env: {},
        }],
        runner_tags: [],
        variables: {},
        artifacts: [],
        services: [],
      }],
    }],
    variables: {},
    trigger_branches: [],
  };
}

/**
 * Validación local espejo LITERAL de _validate_spec (C12)
 * Devuelve array de mensajes en llano (vacío = sin errores)
 */
export function validateSpecLocal(spec: PipelineSpecDraft): string[] {
  const errors: string[] = [];

  // Regla 1: name vacío
  if (!spec.name || spec.name.trim() === "") {
    errors.push("El pipeline necesita un nombre");
  }

  // Regla 2: sin stages
  if (!spec.stages || spec.stages.length === 0) {
    errors.push("Agregá al menos un stage");
  }

  // Regla 3: stage sin jobs
  spec.stages?.forEach((stage, si) => {
    if (!stage.jobs || stage.jobs.length === 0) {
      errors.push(`El stage '${stage.name}' no tiene jobs`);
    }

    // Regla 4: job sin steps
    stage.jobs?.forEach((job) => {
      if (!job.steps || job.steps.length === 0) {
        errors.push(`El job '${job.name}' no tiene steps`);
      }

      // Regla 5: step con script vacío
      job.steps?.forEach((step) => {
        if (!step.script || step.script.trim() === "") {
          errors.push(`El step '${step.name}' no tiene script`);
        }
      });
    });
  });

  // Regla 6: raw_yaml_target inválido
  if (spec.raw_yaml && spec.raw_yaml_target !== "ado" && spec.raw_yaml_target !== "gitlab" && spec.raw_yaml_target !== null) {
    errors.push("Target de YAML crudo inválido");
  }

  return errors;
}

/**
 * Igualdad profunda de specs (para badge "cambios sin guardar" - C15)
 */
export function specsEqual(a: PipelineSpecDraft, b: PipelineSpecDraft): boolean {
  const dictA = JSON.stringify(toSpecDict(a));
  const dictB = JSON.stringify(toSpecDict(b));
  return dictA === dictB;
}

/**
 * Limpia nulls/undefined para serialización JSON
 */
export function toSpecDict(spec: PipelineSpecDraft): object {
  const clean = (obj: any): any => {
    if (obj === null || obj === undefined) return undefined;
    if (Array.isArray(obj)) return obj.map(clean);
    if (typeof obj === "object") {
      const cleaned: any = {};
      for (const [key, value] of Object.entries(obj)) {
        const cleanedValue = clean(value);
        if (cleanedValue !== undefined) {
          cleaned[key] = cleanedValue;
        }
      }
      return cleaned;
    }
    return obj;
  };

  return clean(spec);
}

// ====== Normalizador de specs que llegan del backend (Plan 243 F1, C21) ======

function asArray(value: any): any[] {
  return Array.isArray(value) ? value : [];
}

function asStringArray(value: any): string[] {
  return asArray(value).filter((v) => typeof v === "string");
}

function asRecord(value: any): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(value)) {
    if (v !== null && v !== undefined && typeof v !== "object") out[k] = String(v);
  }
  return out;
}

function asStr(value: any, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asOptStr(value: any): string | null | undefined {
  if (value === null || value === undefined) return undefined;
  return typeof value === "string" ? value : undefined;
}

/**
 * Campos NUEVOS del Plan 243: se normalizan sólo si la fuente los trae.
 *
 * No es un detalle estético. Si el normalizador inyectara `task_steps: []` en todo
 * draft, un draft guardado con el formato del Plan 97 dejaría de ser igual a sí mismo
 * al releerlo y specsEqual() encendería el badge de "cambios sin guardar" sin que el
 * operador haya tocado nada. Presente -> se normaliza; ausente -> sigue ausente.
 */
function optField<T>(raw: any, key: string, map: (v: any) => T): T | undefined {
  return raw && typeof raw === "object" && key in raw ? map(raw[key]) : undefined;
}

function normStep(raw: any): StepDraft {
  const r = raw && typeof raw === "object" ? raw : {};
  return {
    name: asStr(r.name),
    script: asStr(r.script),
    working_directory: asOptStr(r.working_directory),
    condition: asOptStr(r.condition),
    env: asRecord(r.env),
  };
}

function normTaskStep(raw: any): TaskStepDraft {
  const r = raw && typeof raw === "object" ? raw : {};
  return {
    name: asStr(r.name),
    task: asStr(r.task),
    inputs: asRecord(r.inputs),
    condition: asOptStr(r.condition),
    env: asRecord(r.env),
  };
}

function normJob(raw: any): JobDraft {
  const r = raw && typeof raw === "object" ? raw : {};
  return {
    name: asStr(r.name),
    steps: asArray(r.steps).map(normStep),
    image: asOptStr(r.image),
    pool_vm_image: asOptStr(r.pool_vm_image),
    runner_tags: asStringArray(r.runner_tags),
    variables: asRecord(r.variables),
    artifacts: asStringArray(r.artifacts),
    services: asStringArray(r.services),
    task_steps: optField(r, "task_steps", (v) => asArray(v).map(normTaskStep)),
    pool_name: asOptStr(r.pool_name),
    depends_on: optField(r, "depends_on", asStringArray),
    display_name: asOptStr(r.display_name),
  };
}

function normDeployment(raw: any): DeploymentJobDraft {
  const r = raw && typeof raw === "object" ? raw : {};
  return {
    name: asStr(r.name),
    environment: asStr(r.environment),
    strategy: asStr(r.strategy, "runOnce"),
    steps: asArray(r.steps).map(normTaskStep),
    checkout: r.checkout === undefined ? true : Boolean(r.checkout),
    download_artifacts: asStringArray(r.download_artifacts),
    display_name: asOptStr(r.display_name),
  };
}

function normStage(raw: any): StageDraft {
  const r = raw && typeof raw === "object" ? raw : {};
  return {
    name: asStr(r.name),
    jobs: asArray(r.jobs).map(normJob),
    condition: asOptStr(r.condition),
    deployments: optField(r, "deployments", (v) => asArray(v).map(normDeployment)),
    pool_name: asOptStr(r.pool_name),
    pool_vm_image: asOptStr(r.pool_vm_image),
    depends_on: optField(r, "depends_on", asStringArray),
    display_name: asOptStr(r.display_name),
  };
}

/**
 * Normaliza la respuesta de /api/devops/parse-yaml y de cualquier generador backend
 * (las tuplas llegan como arrays por JSON).
 *
 * Plan 243 F1 (C21): antes era `return dict as PipelineSpecDraft`, un cast que no
 * validaba NADA. Ahora es un normalizador real: arrays garantizados, strings con
 * default, records con default {}, y claves desconocidas descartadas. Un dict al que
 * le falte stages[].jobs[].steps ya no rompe el render del builder.
 *
 * ADITIVO por construcción: un draft bien formado del Plan 97 sale idéntico.
 */
export function fromParsedSpec(dict: any): PipelineSpecDraft {
  if (!dict || typeof dict !== "object" || Array.isArray(dict)) {
    return emptySpec();
  }
  const spec: PipelineSpecDraft = {
    name: asStr(dict.name),
    stages: asArray(dict.stages).map(normStage),
    variables: asRecord(dict.variables),
    trigger_branches: asStringArray(dict.trigger_branches),
    raw_yaml: asOptStr(dict.raw_yaml),
    raw_yaml_target:
      dict.raw_yaml_target === "ado" || dict.raw_yaml_target === "gitlab"
        ? dict.raw_yaml_target
        : undefined,
    trigger_disabled: optField(dict, "trigger_disabled", Boolean),
    trigger_paths: optField(dict, "trigger_paths", asStringArray),
    pr_disabled: optField(dict, "pr_disabled", Boolean),
    pool_vm_image: asOptStr(dict.pool_vm_image),
    pool_name: asOptStr(dict.pool_name),
    root_task_steps: optField(dict, "root_task_steps", (v) => asArray(v).map(normTaskStep)),
  };
  // toSpecDict ya limpia los undefined al serializar; acá se devuelven tal cual para
  // que un draft del Plan 97 (sin campos nuevos) siga siendo idéntico a sí mismo.
  return spec;
}

/**
 * Merge drafts en client_profile (FIX C1 - NO borra keys ajenas)
 * GET → merge → PUT (riel §3.10)
 */
export function mergeDraftsIntoProfile(
  profile: object | null,
  drafts: object[]
): object {
  return {
    ...(profile ?? {}),
    devops_pipeline_drafts: drafts,
  };
}

// ====== Operaciones inmutables de stages ======

export function addStage(spec: PipelineSpecDraft): PipelineSpecDraft {
  const nextNum = spec.stages.length + 1;
  return {
    ...spec,
    stages: [
      ...spec.stages,
      {
        name: `stage-${nextNum}`,
        jobs: [],
      },
    ],
  };
}

/**
 * removeSpecVariable — Plan 94 F4. Saca UNA key de spec.variables (inmutable).
 * Usado por "Mover a variable segura": tras crear la variable en el tracker,
 * se quita del spec local (el YAML en HEAD sigue con el valor hasta recommit).
 */
export function removeSpecVariable(spec: PipelineSpecDraft, key: string): PipelineSpecDraft {
  if (!(key in spec.variables)) {
    return spec; // NOOP
  }
  const { [key]: _removed, ...rest } = spec.variables;
  return {
    ...spec,
    variables: rest,
  };
}

export function removeStage(spec: PipelineSpecDraft, stageIndex: number): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  return {
    ...spec,
    stages: spec.stages.filter((_, i) => i !== stageIndex),
  };
}

export function moveStage(spec: PipelineSpecDraft, stageIndex: number, direction: -1 | 1): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const newIndex = stageIndex + direction;
  if (newIndex < 0 || newIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const stages = [...spec.stages];
  const [removed] = stages.splice(stageIndex, 1);
  stages.splice(newIndex, 0, removed);

  return {
    ...spec,
    stages,
  };
}

// ====== Operaciones inmutables de jobs ======

export function addJob(spec: PipelineSpecDraft, stageIndex: number): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const stages = spec.stages.map((s, i) => {
    if (i !== stageIndex) return s;

    return {
      ...s,
      jobs: [
        ...s.jobs,
        {
          name: "job-1",
          steps: [],
          runner_tags: [],
          variables: {},
          artifacts: [],
          services: [],
        },
      ],
    };
  });

  return { ...spec, stages };
}

export function removeJob(spec: PipelineSpecDraft, stageIndex: number, jobIndex: number): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const stages = spec.stages.map((s, si) => {
    if (si !== stageIndex) return s;

    if (jobIndex < 0 || jobIndex >= s.jobs.length) {
      return s; // NOOP
    }

    return {
      ...s,
      jobs: s.jobs.filter((_, ji) => ji !== jobIndex),
    };
  });

  return { ...spec, stages };
}

export function moveJob(spec: PipelineSpecDraft, stageIndex: number, jobIndex: number, direction: -1 | 1): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const stages = spec.stages.map((s, si) => {
    if (si !== stageIndex) return s;

    if (jobIndex < 0 || jobIndex >= s.jobs.length) {
      return s; // NOOP
    }

    const newIndex = jobIndex + direction;
    if (newIndex < 0 || newIndex >= s.jobs.length) {
      return s; // NOOP
    }

    const jobs = [...s.jobs];
    const [removed] = jobs.splice(jobIndex, 1);
    jobs.splice(newIndex, 0, removed);

    return { ...s, jobs };
  });

  return { ...spec, stages };
}

// ====== Operaciones inmutables de steps ======

export function addStep(spec: PipelineSpecDraft, stageIndex: number, jobIndex: number): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const stages = spec.stages.map((s, si) => {
    if (si !== stageIndex) return s;

    if (jobIndex < 0 || jobIndex >= s.jobs.length) {
      return s; // NOOP
    }

    const jobs = s.jobs.map((j, ji) => {
      if (ji !== jobIndex) return j;

      return {
        ...j,
        steps: [
          ...j.steps,
          {
            name: "step-1",
            script: "",
            env: {},
          },
        ],
      };
    });

    return { ...s, jobs };
  });

  return { ...spec, stages };
}

// Plan 97 F1-bis — inserta un step prefabricado (snippet) en un job, inmutable.
// Mismo patrón/guards que addStep; solo cambia que el step llega ya construido
// en vez de crear el placeholder "step-1".
export function appendStep(
  spec: PipelineSpecDraft, stageIndex: number, jobIndex: number, step: StepDraft
): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) return spec;
  const stages = spec.stages.map((s, si) => {
    if (si !== stageIndex) return s;
    if (jobIndex < 0 || jobIndex >= s.jobs.length) return s;
    const jobs = s.jobs.map((j, ji) =>
      ji !== jobIndex ? j : { ...j, steps: [...j.steps, { ...step }] });
    return { ...s, jobs };
  });
  return { ...spec, stages };
}

export function removeStep(spec: PipelineSpecDraft, stageIndex: number, jobIndex: number, stepIndex: number): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const stages = spec.stages.map((s, si) => {
    if (si !== stageIndex) return s;

    if (jobIndex < 0 || jobIndex >= s.jobs.length) {
      return s; // NOOP
    }

    const jobs = s.jobs.map((j, ji) => {
      if (ji !== jobIndex) return j;

      if (stepIndex < 0 || stepIndex >= j.steps.length) {
        return j; // NOOP
      }

      return {
        ...j,
        steps: j.steps.filter((_, sti) => sti !== stepIndex),
      };
    });

    return { ...s, jobs };
  });

  return { ...spec, stages };
}

export function moveStep(spec: PipelineSpecDraft, stageIndex: number, jobIndex: number, stepIndex: number, direction: -1 | 1): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const stages = spec.stages.map((s, si) => {
    if (si !== stageIndex) return s;

    if (jobIndex < 0 || jobIndex >= s.jobs.length) {
      return s; // NOOP
    }

    const jobs = s.jobs.map((j, ji) => {
      if (ji !== jobIndex) return j;

      if (stepIndex < 0 || stepIndex >= j.steps.length) {
        return j; // NOOP
      }

      const newIndex = stepIndex + direction;
      if (newIndex < 0 || newIndex >= j.steps.length) {
        return j; // NOOP
      }

      const steps = [...j.steps];
      const [removed] = steps.splice(stepIndex, 1);
      steps.splice(newIndex, 0, removed);

      return { ...j, steps };
    });

    return { ...s, jobs };
  });

  return { ...spec, stages };
}

// ====== Updates de propiedades ======

export function updateStage(spec: PipelineSpecDraft, stageIndex: number, patch: Partial<StageDraft>): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const stages = spec.stages.map((s, i) => {
    if (i !== stageIndex) return s;
    return { ...s, ...patch };
  });

  return { ...spec, stages };
}

export function updateJob(spec: PipelineSpecDraft, stageIndex: number, jobIndex: number, patch: Partial<JobDraft>): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const stages = spec.stages.map((s, si) => {
    if (si !== stageIndex) return s;

    if (jobIndex < 0 || jobIndex >= s.jobs.length) {
      return s; // NOOP
    }

    const jobs = s.jobs.map((j, ji) => {
      if (ji !== jobIndex) return j;
      return { ...j, ...patch };
    });

    return { ...s, jobs };
  });

  return { ...spec, stages };
}

export function updateStep(spec: PipelineSpecDraft, stageIndex: number, jobIndex: number, stepIndex: number, patch: Partial<StepDraft>): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) {
    return spec; // NOOP
  }

  const stages = spec.stages.map((s, si) => {
    if (si !== stageIndex) return s;

    if (jobIndex < 0 || jobIndex >= s.jobs.length) {
      return s; // NOOP
    }

    const jobs = s.jobs.map((j, ji) => {
      if (ji !== jobIndex) return j;

      if (stepIndex < 0 || stepIndex >= j.steps.length) {
        return j; // NOOP
      }

      const steps = j.steps.map((st, sti) => {
        if (sti !== stepIndex) return st;
        return { ...st, ...patch };
      });

      return { ...j, steps };
    });

    return { ...s, jobs };
  });

  return { ...spec, stages };
}
