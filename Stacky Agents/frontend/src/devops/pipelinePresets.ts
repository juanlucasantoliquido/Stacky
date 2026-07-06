/**
 * pipelinePresets.ts — Plan 97 F0
 * Catálogo ESTÁTICO de presets de pipeline por stack técnico.
 * Cada preset produce un PipelineSpecDraft completo y editable (specBuilder.ts).
 * NUNCA usa scripts de relleno tipo echo — todo comando es el REAL del stack.
 */
import type { PipelineSpecDraft } from "./specBuilder";

export type PresetId = "python" | "node" | "dotnet" | "generic";

export interface PipelinePreset {
  id: PresetId;
  label: string;          // texto del botón/tarjeta en la galería
  description: string;    // 1 frase en llano de qué hace
  build: () => PipelineSpecDraft;  // función pura, siempre devuelve spec NUEVO
}

function preset_python(): PipelineSpecDraft {
  return {
    name: "pipeline-python",
    stages: [{
      name: "build-and-test",
      jobs: [{
        name: "python-job",
        steps: [
          { name: "instalar-dependencias", script: "pip install -r requirements.txt", env: {} },
          { name: "lint", script: "python -m flake8 .", env: {} },
          { name: "test", script: "python -m pytest -q", env: {} },
        ],
        runner_tags: [], variables: {}, artifacts: [], services: [],
      }],
    }],
    variables: {},
    trigger_branches: [],
  };
}

function preset_node(): PipelineSpecDraft {
  return {
    name: "pipeline-node",
    stages: [{
      name: "build-and-test",
      jobs: [{
        name: "node-job",
        steps: [
          { name: "instalar-dependencias", script: "npm ci", env: {} },
          { name: "lint", script: "npm run lint --if-present", env: {} },
          { name: "test", script: "npm test --if-present", env: {} },
          { name: "compilar", script: "npm run build --if-present", env: {} },
        ],
        runner_tags: [], variables: {}, artifacts: [], services: [],
      }],
    }],
    variables: {},
    trigger_branches: [],
  };
}

function preset_dotnet(): PipelineSpecDraft {
  return {
    name: "pipeline-dotnet",
    stages: [{
      name: "build-and-test",
      jobs: [{
        name: "dotnet-job",
        steps: [
          { name: "restaurar", script: "dotnet restore", env: {} },
          { name: "compilar", script: "dotnet build --configuration Release --no-restore", env: {} },
          { name: "test", script: "dotnet test --no-build --configuration Release", env: {} },
        ],
        runner_tags: [], variables: {}, artifacts: [], services: [],
      }],
    }],
    variables: {},
    trigger_branches: [],
  };
}

function preset_generic(): PipelineSpecDraft {
  return {
    name: "pipeline-generico",
    stages: [{
      name: "build-and-test",
      jobs: [{
        name: "generic-job",
        steps: [
          { name: "compilar", script: "echo \"Reemplazá este paso por tu comando de build\"", env: {} },
          { name: "test", script: "echo \"Reemplazá este paso por tu comando de test\"", env: {} },
        ],
        runner_tags: [], variables: {}, artifacts: [], services: [],
      }],
    }],
    variables: {},
    trigger_branches: [],
  };
}

export const PIPELINE_PRESETS: readonly PipelinePreset[] = [
  { id: "python", label: "Python (pip + pytest)", description: "Instala dependencias con pip, corre flake8 y pytest.", build: preset_python },
  { id: "node", label: "Node (npm)", description: "Instala con npm ci, corre lint/test/build si existen los scripts.", build: preset_node },
  { id: "dotnet", label: ".NET (dotnet)", description: "Restaura, compila en Release y corre los tests con dotnet test.", build: preset_dotnet },
  { id: "generic", label: "Genérico (sin stack detectado)", description: "Plantilla neutra: reemplazá los comandos por los tuyos.", build: preset_generic },
];

export function getPresetById(id: PresetId): PipelinePreset {
  const p = PIPELINE_PRESETS.find((x) => x.id === id);
  if (!p) throw new Error(`Preset desconocido: ${id}`);
  return p;
}
