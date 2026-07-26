/** Plan 250 F4 — modelo PURO del panel de edición quirúrgica.
 *  Sin DOM, sin React, sin fetch: toda la lógica testeable vive acá y el .tsx es sólo
 *  cableado (en este frontend no hay jsdom ni @testing-library/react, así que un panel
 *  con lógica adentro sería lógica sin tests). */

/** Espejo de components/dbcompare/lineDiff.ts:12 (MAX_LINES). `buildDiffLines`
 *  (components/devops/pipelineLint.ts:91) arma una matriz LCS O(n·m) SIN cap propio:
 *  el cap lo pone este modelo y es OBLIGATORIO, o la UI se cuelga con un YAML grande. */
export const MAX_EDIT_LINES = 3000;

export const EDIT_VERBS = [
  'add_step',
  'remove_step',
  'move_step',
  'set_task_input',
  'add_stage',
  'set_trigger_paths',
  'set_schedule',
] as const;

export type EditVerb = (typeof EDIT_VERBS)[number];
export type EditPosition = 'before' | 'after' | 'end';

export interface EditFormState {
  /** C5 — de dónde sale el YAML: vía A (pegar), siempre disponible y sin dependencias. */
  beforeYaml: string;
  /** Ruta en el repo (p. ej. `pipelines/ci-cd-online.yml`), usada tal cual en /commit. */
  repoPath: string;
  verb: EditVerb | '';
  targetPath: string;
  anchorRef: string | null;
  position: EditPosition;
  taskRef: string | null;
  inputs: Record<string, string>;
  displayName: string;
}

export interface Hunk {
  start_line: number;
  end_line: number;
  before: string[];
  after: string[];
  reason: string;
}

export interface PreservationDto {
  ok: boolean;
  comments_before: number;
  comments_after: number;
  unsupported_lost: string[];
  lines_untouched: number;
  lines_total_before: number;
  detail: string;
}

export interface EditHealth {
  pipeline_nl_edit_enabled?: boolean;
  pipeline_nl_edit_commit_enabled?: boolean;
}

export const emptyEditForm = (): EditFormState => ({
  beforeYaml: '',
  repoPath: '',
  verb: '',
  targetPath: '',
  anchorRef: null,
  position: 'end',
  taskRef: null,
  inputs: {},
  displayName: '',
});

const NEEDS_TASK: ReadonlySet<string> = new Set(['add_step', 'set_task_input']);
const NEEDS_TARGET: ReadonlySet<string> = new Set([
  'add_step',
  'remove_step',
  'move_step',
  'set_task_input',
]);
const NEEDS_ANCHOR: ReadonlySet<string> = new Set(['remove_step', 'move_step', 'set_task_input']);

/** Habilita "Ver diff" sólo si el formulario está completo PARA ESE VERBO. */
export function isPlanRequestReady(s: EditFormState): boolean {
  if (!s.beforeYaml.trim()) return false;
  if (!s.repoPath.trim()) return false;
  if (!s.verb) return false;
  if (NEEDS_TARGET.has(s.verb) && !s.targetPath.trim()) return false;
  if (NEEDS_TASK.has(s.verb) && !(s.taskRef || '').trim()) return false;
  if (NEEDS_ANCHOR.has(s.verb) && !(s.anchorRef || '').trim()) return false;
  return true;
}

/** Resumen en español del cambio, DERIVADO de los hunks. Nunca redactado por un LLM. */
export function summarizeHunks(hunks: Hunk[]): string {
  if (!hunks || hunks.length === 0) return 'sin cambios';
  let agregados = 0;
  let quitados = 0;
  let modificados = 0;
  for (const h of hunks) {
    const tieneAntes = (h.before || []).length > 0;
    const tieneDespues = (h.after || []).length > 0;
    if (!tieneAntes && tieneDespues) agregados += 1;
    else if (tieneAntes && !tieneDespues) quitados += 1;
    else modificados += 1;
  }
  const partes: string[] = [];
  if (agregados) partes.push(`${agregados} bloque${agregados === 1 ? '' : 's'} agregado${agregados === 1 ? '' : 's'}`);
  if (quitados) partes.push(`${quitados} bloque${quitados === 1 ? '' : 's'} quitado${quitados === 1 ? '' : 's'}`);
  if (modificados) partes.push(`${modificados} bloque${modificados === 1 ? '' : 's'} modificado${modificados === 1 ? '' : 's'}`);
  return partes.join(', ');
}

/** Contrato Plan 106 F5 (PipelineBuilderSection.tsx:382-383): PRE-RELLENA sólo lo
 *  vacío. NUNCA pisa un campo que el operador ya escribió. */
export function prefillOnlyEmpty(
  current: EditFormState,
  suggested: Partial<EditFormState>,
): EditFormState {
  const out: EditFormState = { ...current };
  for (const clave of Object.keys(suggested) as Array<keyof EditFormState>) {
    const propuesto = suggested[clave];
    if (propuesto === undefined || propuesto === null) continue;
    const actual = out[clave];
    const vacio =
      actual === null ||
      actual === undefined ||
      (typeof actual === 'string' && actual.trim() === '') ||
      (clave === 'inputs' && Object.keys((actual as Record<string, string>) || {}).length === 0);
    if (!vacio) continue;
    (out as unknown as Record<string, unknown>)[clave] = propuesto;
  }
  return out;
}

/** Gate de tamaño: por encima del cap no se pide diff (se ofrece el YAML crudo). */
export function canRenderDiff(before: string, after: string): boolean {
  const a = (before || '').split('\n').length;
  const b = (after || '').split('\n').length;
  return a <= MAX_EDIT_LINES && b <= MAX_EDIT_LINES;
}

export type CommitBlockReason =
  | 'ok'
  | 'flag_commit_off'
  | 'sin_diff'
  | 'gates_en_rojo'
  | 'sin_confirmar'
  | 'formulario_incompleto';

/** Un botón muerto no enseña nada: además de poder/no poder, devuelve POR QUÉ. */
export function canCommit(
  state: EditFormState,
  health: EditHealth | null | undefined,
  opts: { reviewOk: boolean | null; confirmChecked: boolean; hasHunks: boolean },
): { allowed: boolean; reason: CommitBlockReason } {
  if (!health?.pipeline_nl_edit_commit_enabled) return { allowed: false, reason: 'flag_commit_off' };
  if (!isPlanRequestReady(state)) return { allowed: false, reason: 'formulario_incompleto' };
  if (!opts.hasHunks) return { allowed: false, reason: 'sin_diff' };
  if (opts.reviewOk !== true) return { allowed: false, reason: 'gates_en_rojo' };
  if (!opts.confirmChecked) return { allowed: false, reason: 'sin_confirmar' };
  return { allowed: true, reason: 'ok' };
}

export const COMMIT_BLOCK_COPY: Record<CommitBlockReason, string> = {
  ok: '',
  flag_commit_off:
    'Guardar en el repositorio está apagado de fábrica. Activá STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED en Configuración → Arnés. Mientras tanto podés copiar el YAML.',
  sin_diff: 'Pedí el diff primero: no hay ningún cambio para guardar.',
  gates_en_rojo: 'El cambio introduce un problema nuevo. Revisá el semáforo antes de guardarlo.',
  sin_confirmar: 'Tildá la confirmación para habilitar el guardado.',
  formulario_incompleto: 'Completá el YAML, la ruta en el repo y los datos del cambio.',
};

/** Sello de preservación en UNA línea, al lado del semáforo, antes del botón. */
export function formatPreservation(p: PreservationDto | null | undefined): string {
  if (!p) return '';
  const base = `Se preservan ${p.comments_after}/${p.comments_before} comentarios y ${p.unsupported_lost.length} construcciones no modeladas; ${p.lines_untouched} de ${p.lines_total_before} líneas quedan byte-idénticas.`;
  if (p.ok) return base;
  const perdidas = p.unsupported_lost.length
    ? ` Se perdería: ${p.unsupported_lost.join(', ')}.`
    : '';
  return `${base}${perdidas}${p.detail ? ` ${p.detail}` : ''}`;
}
