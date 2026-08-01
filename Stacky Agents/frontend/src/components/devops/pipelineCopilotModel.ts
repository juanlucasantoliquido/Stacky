/**
 * pipelineCopilotModel.ts — Plan 279 F8. Logica PURA del copiloto de pipelines.
 *
 * El repo NO tiene RTL ni jsdom, asi que toda la logica testeable vive aca y el
 * .tsx queda como cascaron de presentacion. Sin DOM, sin red, sin estado global.
 *
 * Espejo del backend: services/pipeline_session.py (los 8 estados) y las 6
 * acciones de services/devops_action_catalog.py.
 */

export type SessionState =
  | 'intake' | 'discovery' | 'draft' | 'review'
  | 'secrets' | 'confirm' | 'committed' | 'failed';

/** Espejo de PIPELINE_SESSION_STATES (backend). Mismo orden. */
export const SESSION_STATES: SessionState[] = [
  'intake', 'discovery', 'draft', 'review',
  'secrets', 'confirm', 'committed', 'failed',
];

/** Los 6 ids que el Plan 279 agrega al catalogo. Espejo literal del .py. */
export const COPILOT_ACTION_IDS = [
  'devops.pipeline_new.draft',
  'devops.pipeline_new.lint',
  'devops.pipeline_new.explain',
  'devops.pipeline_new.preflight',
  'devops.pipeline_new.secrets',
  'devops.pipeline_new.commit',
] as const;

/** La UNICA accion de escritura del plan. */
export const COPILOT_WRITE_ACTION_ID = 'devops.pipeline_new.commit';

const STATE_LABELS: Record<SessionState, string> = {
  intake: 'Contame qué pipeline necesitás',
  discovery: 'Reconociendo el proyecto y el proveedor',
  draft: 'Borrador armado',
  review: 'Borrador revisado',
  secrets: 'Faltan variables por cargar',
  confirm: 'Esperando tu confirmación',
  committed: 'Pipeline creada en el repositorio',
  failed: 'La sesión se detuvo',
};

/** Texto del paso actual, en castellano. Nunca vacio. */
export function stateLabel(s: SessionState): string {
  return STATE_LABELS[s] ?? 'Paso desconocido';
}

const AVAILABLE_BY_STATE: Record<SessionState, string[]> = {
  // Todavia no hay borrador: lo unico ofrecible es armarlo.
  intake: ['devops.pipeline_new.draft'],
  discovery: ['devops.pipeline_new.draft'],
  // Con borrador en mano, se puede revisar, explicar, chequear y ver variables.
  draft: [
    'devops.pipeline_new.lint',
    'devops.pipeline_new.explain',
    'devops.pipeline_new.preflight',
    'devops.pipeline_new.secrets',
  ],
  review: [
    'devops.pipeline_new.lint',
    'devops.pipeline_new.explain',
    'devops.pipeline_new.preflight',
    'devops.pipeline_new.secrets',
  ],
  secrets: [
    'devops.pipeline_new.secrets',
    'devops.pipeline_new.preflight',
  ],
  // El UNICO estado que ofrece la escritura.
  confirm: [COPILOT_WRITE_ACTION_ID],
  // Terminales: no se ofrece nada.
  committed: [],
  failed: [],
};

/** Que se le ofrece al operador en cada estado. Determinista. */
export function availableActionIds(s: SessionState): string[] {
  return [...(AVAILABLE_BY_STATE[s] ?? [])];
}

/** true si el estado exige confirmacion explicita antes de seguir. */
export function needsOperatorConfirmation(s: SessionState): boolean {
  return s === 'confirm';
}

/**
 * [ADICION ARQUITECTO] true si la tarjeta DEBE mostrar el undo_hint antes del
 * boton de confirmar. Determinista: 'review' | 'secrets' | 'confirm'.
 *
 * Se muestra ANTES de 'confirm' a proposito: el operador tiene que ver como
 * deshacer mientras todavia esta decidiendo, no cuando ya apreto.
 */
export function mustShowUndoHint(s: SessionState): boolean {
  return s === 'review' || s === 'secrets' || s === 'confirm';
}

/**
 * Los 3 runtimes que el copiloto soporta, con su modo. Espejo de F6.
 *
 * `github_copilot` no tiene turno CLI: el backend responde 200 con
 * mode:"deterministic" y el operador conserva la capacidad completa via matcher
 * determinista + tarjeta de accion. Degradacion DECLARADA, no falla.
 */
export const COPILOT_RUNTIMES: { id: string; label: string; mode: 'cli' | 'deterministic' }[] = [
  { id: 'claude_code_cli', label: 'Claude Code (recomendado)', mode: 'cli' },
  { id: 'codex_cli', label: 'Codex', mode: 'cli' },
  { id: 'github_copilot', label: 'GitHub Copilot (modo determinista)', mode: 'deterministic' },
];
