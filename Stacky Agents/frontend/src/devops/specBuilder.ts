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

export interface JobDraft {
  name: string;
  steps: StepDraft[];
  image?: string | null;
  pool_vm_image?: string | null;
  runner_tags: string[];
  variables: Record<string, string>;
  artifacts: string[];
  services: string[];
}

export interface StageDraft {
  name: string;
  jobs: JobDraft[];
  condition?: string | null;
}

export interface PipelineSpecDraft {
  name: string;
  stages: StageDraft[];
  variables: Record<string, string>;
  trigger_branches: string[];
  raw_yaml?: string | null;
  raw_yaml_target?: "ado" | "gitlab" | null;
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

/**
 * Normaliza la respuesta de /api/devops/parse-yaml
 * (las tuplas llegan como arrays por JSON)
 */
export function fromParsedSpec(dict: any): PipelineSpecDraft {
  return dict as PipelineSpecDraft;
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
