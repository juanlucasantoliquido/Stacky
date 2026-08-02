/**
 * clientProfileCopilotModel.ts — Plan 296 F6. Logica PURA del copiloto del perfil.
 *
 * El repo NO tiene RTL ni jsdom, asi que toda la logica testeable vive aca y el
 * .tsx queda como cascaron de presentacion. Sin DOM, sin red, sin estado global.
 *
 * Espejo del backend: services/profile_copilot_session.py (los 7 estados),
 * services/runtime_capabilities.py:31 (RUNTIMES) y
 * services/runtime_profile.py (FICHA_CAMPOS).
 *
 * REGLA DE UI INNEGOCIABLE (viene de un incidente real del repo): un control que
 * no se puede usar SE DESHABILITA CON EL MOTIVO A LA VISTA; nunca se esconde.
 * Por eso accionesDisponibles devuelve SIEMPRE las mismas acciones, con
 * `habilitado` + `motivo`, y el .tsx las renderiza todas.
 */

export type ProfileSessionState =
  | 'eleccion_runtime'
  | 'diagnostico'
  | 'preguntando'
  | 'propuesta'
  | 'confirmando'
  | 'aplicado'
  | 'detenido';

/** Espejo de PROFILE_SESSION_STATES. Mismo orden. */
export const PROFILE_SESSION_STATES: ProfileSessionState[] = [
  'eleccion_runtime',
  'diagnostico',
  'preguntando',
  'propuesta',
  'confirmando',
  'aplicado',
  'detenido',
];

/** Espejo LITERAL de runtime_capabilities.RUNTIMES (services/runtime_capabilities.py:31). */
export const RUNTIMES = ['claude_code_cli', 'codex_cli', 'github_copilot'] as const;
export type RuntimeId = (typeof RUNTIMES)[number];

/** Espejo de runtime_profile.FICHA_CAMPOS. */
export const FICHA_CAMPOS = [
  'disponible',
  'recomendado_para',
  'capacidades',
  'credenciales',
  'ejecucion',
  'si_falla',
  'como_cambiar',
] as const;

export const RUNTIME_LABEL: Record<RuntimeId, string> = {
  claude_code_cli: 'Claude',
  codex_cli: 'Codex',
  github_copilot: 'GitHub Copilot',
};

const STATE_LABELS: Record<ProfileSessionState, string> = {
  eleccion_runtime: 'Elegí con qué motor querés trabajar',
  diagnostico: 'Revisando qué falta en el perfil',
  preguntando: 'Hay una pregunta abierta',
  propuesta: 'Propuesta lista para revisar',
  confirmando: 'Esperando tu confirmación',
  aplicado: 'El perfil quedó guardado',
  detenido: 'La conversación se detuvo',
};

const TERMINALES: string[] = ['aplicado', 'detenido'];

/** Texto del paso actual, en castellano. Nunca vacio. */
export function stateLabel(s: ProfileSessionState | string): string {
  return STATE_LABELS[s as ProfileSessionState] ?? 'Paso desconocido';
}

/** Nunca inventa: un id que no conocemos se muestra crudo. */
export function runtimeLabel(id: string): string {
  return RUNTIME_LABEL[id as RuntimeId] ?? id;
}

export type AccionCopiloto = { id: string; habilitado: boolean; motivo: string };

const MOTIVO_APPLY_OFF =
  'Aplicar cambios al perfil está apagado. Se puede activar desde Configuración > Arnés ' +
  '(STACKY_PROFILE_COPILOT_APPLY_ENABLED).';

/**
 * Un boton por accion; NUNCA se esconde: se deshabilita CON motivo.
 * El largo de la lista es el MISMO con apply encendido o apagado.
 */
export function accionesDisponibles(
  s: ProfileSessionState | string,
  applyHabilitado: boolean
): AccionCopiloto[] {
  const estado = String(s ?? '');
  const conocido = (PROFILE_SESSION_STATES as string[]).includes(estado);
  const terminal = TERMINALES.includes(estado);

  const motivoTerminal = terminal
    ? 'Esta conversación ya terminó: abrí una nueva para seguir configurando.'
    : '';
  const motivoDesconocido = conocido
    ? ''
    : 'No reconozco el paso en el que quedó la conversación: volvé a empezar.';
  const bloqueo = motivoTerminal || motivoDesconocido;

  const responder: AccionCopiloto = {
    id: 'responder',
    habilitado: !bloqueo && (estado === 'preguntando' || estado === 'diagnostico'),
    motivo:
      bloqueo ||
      (estado === 'preguntando' || estado === 'diagnostico'
        ? ''
        : 'Todavía no hay una pregunta abierta.'),
  };

  const proponer: AccionCopiloto = {
    id: 'proponer',
    habilitado:
      !bloqueo && ['diagnostico', 'preguntando', 'propuesta'].includes(estado),
    motivo:
      bloqueo ||
      (['diagnostico', 'preguntando', 'propuesta'].includes(estado)
        ? ''
        : 'Elegí primero el motor de ejecución.'),
  };

  const puedeAplicar = !bloqueo && ['propuesta', 'confirmando'].includes(estado);
  const aplicar: AccionCopiloto = {
    id: 'aplicar',
    habilitado: puedeAplicar && applyHabilitado,
    motivo: !applyHabilitado
      ? MOTIVO_APPLY_OFF
      : bloqueo || (puedeAplicar ? '' : 'Primero revisá la propuesta de cambios.'),
  };

  const cambiarRuntime: AccionCopiloto = {
    id: 'cambiar_runtime',
    habilitado: puedeElegirRuntime(estado),
    motivo: puedeElegirRuntime(estado)
      ? ''
      : bloqueo || 'El motor sólo se puede cambiar antes de ejecutar una acción.',
  };

  return [responder, proponer, aplicar, cambiarRuntime];
}

/**
 * Motivo por el que el boton de aplicar queda deshabilitado ademas de por la
 * flag: una propuesta que deja el perfil invalido no se puede aplicar, y el
 * motivo se muestra (deshabilitar y explicar, nunca esconder).
 */
export function motivoAplicarInvalido(validacionPrevia: {
  ok?: boolean;
  errors?: string[];
}): string {
  if (!validacionPrevia || validacionPrevia.ok !== false) return '';
  const primero = (validacionPrevia.errors ?? [])[0] ?? 'no dice por qué';
  return `La propuesta deja el perfil inválido: ${primero}.`;
}

/** Campos de FICHA_CAMPOS que la ficha recibida NO trae. */
export function fichaIncompleta(ficha: Record<string, unknown>): string[] {
  const presente = ficha ?? {};
  return FICHA_CAMPOS.filter((c) => !(c in presente));
}

export function progresoTexto(c: {
  requeridas_ok: number;
  requeridas_total: number;
}): string {
  const ok = Number(c?.requeridas_ok ?? 0);
  const total = Number(c?.requeridas_total ?? 0);
  return `${ok} de ${total} secciones obligatorias`;
}

/** El motor solo se elige ANTES de ejecutar: en terminales ya no. */
export function puedeElegirRuntime(s: ProfileSessionState | string): boolean {
  const estado = String(s ?? '');
  if (!(PROFILE_SESSION_STATES as string[]).includes(estado)) return false;
  return !TERMINALES.includes(estado);
}

/** Devuelve el texto del backend TAL CUAL. Nunca redacta uno propio. */
export function motivoRuntimeNoDisponible(ficha: Record<string, unknown>): string {
  const motivo = (ficha ?? {}).disponibilidad_motivo;
  return typeof motivo === 'string' ? motivo : '';
}
