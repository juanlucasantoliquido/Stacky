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

// ===========================================================================
// Plan 288 — el copiloto se usa LOCAL y el destino lo decide el proyecto.
//
// Lo que estaba roto: la seccion no tenia forma de abrir un hilo (el
// `conversationId` era una constante `null`), asi que SIEMPRE mostraba
// "abri uno en la seccion Agente DevOps" y ahi moria. Y el destino de la
// escritura salia de `draftProvider()` (services/devopsActionBindings.ts:63),
// que devuelve 'ado' salvo que alguien haya puesto 'gitlab' en los params.
// ===========================================================================

export type CopilotRuntimeId = 'claude_code_cli' | 'codex_cli' | 'github_copilot';

const RUNTIME_IDS = COPILOT_RUNTIMES.map((r) => r.id);

/** Runtime valido, o 'claude_code_cli'. Un id inventado NO viaja al backend. */
export function normalizeCopilotRuntime(runtime?: string | null): CopilotRuntimeId {
  const r = String(runtime ?? '').trim();
  return (RUNTIME_IDS.includes(r) ? r : 'claude_code_cli') as CopilotRuntimeId;
}

export interface CopilotStartBody {
  project: string;
  message: string;
  runtime: CopilotRuntimeId;
  /** Sella el hilo como sesion del copiloto (api/devops_agent.py:155-158). */
  pipeline_session: { state: SessionState; version: string };
}

/**
 * Cuerpo del POST que ABRE el hilo del copiloto.
 *
 * SIN `server_alias` a proposito, y no es un olvido: ese campo es lo unico que
 * ata el turno a un servidor remoto (api/devops_agent.py:144-149). Omitirlo es
 * lo que hace que el copiloto corra LOCAL, sobre el repo del proyecto, sin
 * exigirle al operador tener ningun host configurado.
 */
export function copilotStartBody(args: {
  project: string;
  message: string;
  runtime?: string | null;
}): CopilotStartBody {
  return {
    project: args.project,
    message: args.message,
    runtime: normalizeCopilotRuntime(args.runtime),
    pipeline_session: { state: 'intake', version: '1' },
  };
}

export interface CopilotTargetPayload {
  provider?: string | null;
  provider_source?: string | null;
  pipeline_file?: string | null;
}

export interface CopilotTarget {
  /** '' cuando el proyecto no lo declara. NUNCA 'ado' por defecto. */
  provider: '' | 'ado' | 'gitlab';
  /** Nombre del archivo que se va a crear, o '' si no hay destino. */
  file: string;
  blocked: boolean;
  message: string;
}

/** Espejo de PIPELINE_FILENAME (services/pipeline_session.py:45-48). */
const PIPELINE_FILE: Record<'ado' | 'gitlab', string> = {
  ado: 'azure-pipelines.yml',
  gitlab: '.gitlab-ci.yml',
};

const SIN_DESTINO =
  'Este proyecto no declara a qué tracker escribir, así que el copiloto no ' +
  'puede saber si la pipeline va a Azure DevOps o a GitLab. Configurá el ' +
  'tracker del proyecto (Configuración → Proyectos) y volvé.';

/**
 * A dónde escribe el copiloto, según lo que DECLARA el proyecto.
 *
 * Solo acepta `provider_source === 'project'`: un provider que no venga del
 * proyecto es exactamente el default silencioso que este plan mata. Ante la
 * duda BLOQUEA y lo explica, en vez de escribir `azure-pipelines.yml` dentro
 * de un repo de GitLab.
 */
export function resolveCopilotTarget(
  payload: CopilotTargetPayload | null | undefined,
): CopilotTarget {
  const provider = String(payload?.provider ?? '').trim();
  const source = String(payload?.provider_source ?? '').trim();
  if (source !== 'project' || (provider !== 'ado' && provider !== 'gitlab')) {
    return { provider: '', file: '', blocked: true, message: SIN_DESTINO };
  }
  const file = String(payload?.pipeline_file ?? '').trim() || PIPELINE_FILE[provider];
  return { provider, file, blocked: false, message: '' };
}

/**
 * Flags que le faltan al copiloto para poder ESCRIBIR la pipeline, por nombre.
 *
 * Las dos nacen OFF a proposito (escriben en el repositorio real del operador),
 * pero hasta ahora el copiloto no lo decia: el operador llegaba hasta el final
 * y la accion aparecia bloqueada sin explicacion. Degradacion HONESTA, mismo
 * criterio que `unavailable_reason` del backend.
 *
 * Ausente cuenta como OFF: un health viejo avisa de mas, nunca de menos.
 */
export function missingWriteFlags(
  health: Record<string, boolean | undefined> | null | undefined,
): string[] {
  const h = health ?? {};
  const faltan: string[] = [];
  if (h.pipeline_copilot_commit_enabled !== true) {
    faltan.push('STACKY_PIPELINE_COPILOT_COMMIT_ENABLED');
  }
  if (h.agent_action_run_enabled !== true) {
    faltan.push('STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED');
  }
  return faltan;
}

export interface CopilotConversationLike {
  conversation_id: number;
  pipeline_copilot?: boolean;
}

/**
 * Id del hilo del copiloto a retomar, o null.
 *
 * La seccion promete por escrito que "la sesion se retoma sola, en el paso
 * donde quedo". Esto la cumple. `pipeline_copilot` lo declara el backend
 * (api/devops_agent.py, list_conversations); un hilo de chat libre NUNCA se
 * adopta: mostraria un estado de pipeline que esa conversacion no tiene.
 */
export function pickCopilotConversation(
  items: CopilotConversationLike[] | null | undefined,
): number | null {
  // El backend lista por id descendente => el primero que califica es el mas
  // reciente. No se reordena aca para no depender de dos criterios distintos.
  const hit = (items ?? []).find((c) => c?.pipeline_copilot === true);
  return hit ? hit.conversation_id : null;
}
