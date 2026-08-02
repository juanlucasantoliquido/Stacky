/**
 * pipelineWizardModel.ts — Plan 294 F8. Logica PURA del asistente guiado.
 *
 * Sin DOM, sin red, sin estado global. Es lo unico testeable del asistente:
 * este repo no tiene RTL ni jsdom, asi que el .tsx queda de cascaron.
 *
 * NO ES UNA SEGUNDA MAQUINA DE ESTADOS. `WIZARD_STEPS` es la navegacion de
 * PANTALLAS; cada pantalla se proyecta con `stepState()` al estado canonico de
 * la maquina de sesion que ya existe (plan 279), cuya lista se IMPORTA — no se
 * copia a mano.
 *
 * R4 (riel duro): la eleccion de runtime no se degrada nunca en silencio.
 * `strictRuntime` devuelve el PEDIDO o null. El asistente tiene PROHIBIDO
 * rutear su eleccion por el normalizador permisivo del copiloto, que ante un id
 * desconocido cae al primero sin avisar: eso es exactamente lo que R4 prohibe.
 */
import type { StepDef } from '../ui/stepperModel';
import { nextStepId, prevStepId } from '../ui/stepperModel';
import { SESSION_STATES, type SessionState } from './pipelineCopilotModel';

export const WIZARD_STEPS: StepDef[] = [
  { id: 'p1', label: 'Esto es lo que veo de tu proyecto' },
  { id: 'p2', label: 'Que queres lograr' },
  { id: 'p3', label: 'Un par de datos' },
  { id: 'p4', label: 'Quien lo va a hacer' },
  { id: 'p5', label: 'Preparando tu pipeline' },
  { id: 'p6', label: 'Esto es lo que va a pasar' },
  { id: 'p7', label: 'Confirma' },
];

/**
 * Espejo cliente de WIZARD_STEP_TO_STATE (services/pipeline_intent.py).
 * Los VALORES se validan contra SESSION_STATES importado: la lista de estados
 * no se copia a mano en ningun lado.
 */
const STEP_TO_STATE: Record<string, SessionState> = {
  p1: 'discovery',
  p2: 'discovery',
  p3: 'discovery',
  p4: 'discovery',
  p5: 'draft',
  p6: 'review',
  p7: 'confirm',
};

/** Estado canonico de sesion que le corresponde a una pantalla del asistente. */
export function stepState(stepId: string): string {
  const estado = STEP_TO_STATE[stepId];
  return SESSION_STATES.includes(estado) ? estado : '';
}

export interface WizardState {
  step: string;
  answers: Record<string, string>;
  goal: string;
  runtime: string;
  intent: Record<string, unknown>;
  done: string[];
}

export interface ProbePayload {
  project?: string;
  repository?: string;
  provider?: string;
  default_branch?: string;
  stack?: string;
  framework?: string;
  package_manager?: string;
  build_command?: string;
  test_command?: string;
  variables?: string[];
}

export function emptyWizardState(): WizardState {
  return { step: 'p1', answers: {}, goal: '', runtime: '', intent: {}, done: [] };
}

/** Motivo EN CASTELLANO por el que todavia no se puede avanzar. */
export function canAdvance(s: WizardState): { ok: boolean; reason: string } {
  if (s.step === 'p2' && !s.goal.trim()) {
    return { ok: false, reason: 'Eleg' + 'i que queres lograr para poder seguir.' };
  }
  if (s.step === 'p4' && !s.runtime.trim()) {
    return { ok: false, reason: 'Eleg' + 'i quien va a armar la pipeline.' };
  }
  if (s.step === 'p7') {
    return { ok: false, reason: 'Este es el ultimo paso: eleg' + 'i una de las acciones.' };
  }
  return { ok: true, reason: '' };
}

/** No avanza si `canAdvance` dice que no. El paso queda donde estaba. */
export function advanceWizard(s: WizardState): WizardState {
  if (!canAdvance(s).ok) return s;
  const siguiente = nextStepId(WIZARD_STEPS, s.step);
  if (!siguiente) return s;
  const done = s.done.includes(s.step) ? s.done : [...s.done, s.step];
  return { ...s, step: siguiente, done };
}

/** R8 — volver NO pierde informacion: `answers` viaja intacto. */
export function goBack(s: WizardState): WizardState {
  const anterior = prevStepId(WIZARD_STEPS, s.step);
  if (!anterior) return s;
  return { ...s, step: anterior };
}

/** Nombres, jamas valores: un elemento con "=" o ":" es un valor colado. */
function soloNombres(crudos: unknown): string[] {
  const lista = Array.isArray(crudos)
    ? crudos
    : String(crudos ?? '').split(',');
  return lista
    .map((v) => String(v ?? '').trim())
    .filter((v) => v.length > 0 && !v.includes('=') && !v.includes(':'));
}

/** Arma el cuerpo que el backend espera. Las 24 claves del contrato, ni una mas. */
export function buildIntent(s: WizardState, probe: ProbePayload): Record<string, unknown> {
  const a = s.answers ?? {};
  const ramas = soloNombres(a.branches ?? probe.default_branch ?? '');
  return {
    schema_version: '1',
    project: probe.project ?? '',
    repository: probe.repository ?? '',
    provider: probe.provider ?? '',
    default_branch: probe.default_branch ?? '',
    stack: probe.stack ?? '',
    framework: probe.framework ?? '',
    package_manager: probe.package_manager ?? '',
    goal: s.goal,
    pipeline_kind: a.pipeline_kind ?? '',
    triggers: ramas,
    stages: soloNombres(a.stages ?? ''),
    build_command: a.build_command ?? probe.build_command ?? '',
    test_command: a.test_command ?? probe.test_command ?? '',
    coverage: String(a.coverage ?? '').toLowerCase() === 'si',
    artifacts: soloNombres(a.artifact_path ?? ''),
    environments: soloNombres(a.deploy_environment ?? ''),
    deploy_target: a.deploy_target ?? '',
    variables: soloNombres(a.variables ?? probe.variables ?? []),
    required_secrets: soloNombres(a.required_secrets ?? ''),
    runtime: s.runtime,
    constraints: soloNombres(a.constraints ?? ''),
    existing_pipeline_key: a.existing_pipeline ?? '',
    free_text: a.free_text ?? a.change_description ?? '',
  };
}

export function serializeDraft(s: WizardState): string {
  return JSON.stringify(s);
}

/** Tolera basura: devuelve null en vez de lanzar. */
export function parseDraft(raw: string | null): WizardState | null {
  if (!raw) return null;
  try {
    const d = JSON.parse(raw);
    if (!d || typeof d !== 'object') return null;
    if (typeof d.step !== 'string' || !Array.isArray(d.done)) return null;
    return d as WizardState;
  } catch {
    return null;
  }
}

// ── R4 — la eleccion del usuario se respeta o se detiene. Nunca se cambia ────

export const WIZARD_RUNTIME_IDS = ['claude_code_cli', 'codex_cli', 'github_copilot'] as const;

/**
 * Devuelve `pedido` si esta disponible, o null. JAMAS otro runtime.
 * El null obliga a la pantalla a pedirle al usuario que elija de nuevo, con los
 * tres botones a la vista. No existe camino en el que el runtime efectivo
 * difiera del solicitado sin que el usuario haya vuelto a elegir.
 */
export function strictRuntime(pedido: string, disponibles: string[]): string | null {
  const p = String(pedido ?? '').trim();
  if (!p) return null;
  return (disponibles ?? []).includes(p) ? p : null;
}

/** Alias historico del plan: MISMA semantica que strictRuntime. */
export function resolveWizardRuntime(pedido: string, disponibles: string[]): string | null {
  return strictRuntime(pedido, disponibles);
}

// ── R2 — los 4 actos del ultimo paso no se encadenan NUNCA ───────────────────

export const WIZARD_ACT_IDS = [
  'guardar_borrador',
  'crear_archivo',
  'registrar_definicion',
  'ejecutar',
] as const;

/**
 * SIEMPRE null. Existe para que la AUSENCIA de encadenamiento sea testeable y
 * no una promesa de prosa: no hay "siguiente acto automatico". Hacer uno no
 * dispara el que sigue, y el disparo nunca es automatico.
 */
export function nextActAfter(_act: string): null {
  return null;
}
