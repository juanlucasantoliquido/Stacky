/** Plan 251 F5 — modelo PURO de la matriz de entornos. Sin React, sin fetch, sin DOM.
 *  Tipos espejo del contrato §4.2 (backend services/pipeline_environments.py). */

export type CellState = 'definido' | 'default' | 'falta' | 'manual';
export type ValueKind =
  | 'variable'
  | 'secret'
  | 'service_connection'
  | 'server'
  | 'deploy_path'
  | 'parameter';

export interface EnvCell {
  state: CellState;
  source: string;
  note: string | null;
}

export interface EnvCellRow extends EnvCell {
  requirement: string;
  environment: string;
}

export interface EnvRequirement {
  name: string;
  kind: ValueKind;
  provider: string;
  is_secret: boolean;
  declared_default: string | null;
  per_environment: boolean;
  confidence: 'alta' | 'baja';
  note?: string | null;
  evidence: Array<{ path: string; excerpt: string }>;
}

export interface EnvMatrixResponse {
  environments: string[];
  requirements: EnvRequirement[];
  cells: EnvCellRow[];
  pending_count: number;
  pending_fingerprint: string;
  degraded: string[];
  provider: string;
}

/** Separador de unidad (U+001F). PROHIBIDO el byte NUL en cualquier clave que pueda
 *  llegar a serializarse: esta clave se arma del lado del CLIENTE y nunca viaja. */
const SEP = '';

/** indexCells — el mapa de lookup para pintar la tabla, construido UNA vez. */
export function indexCells(m: EnvMatrixResponse): Map<string, EnvCellRow> {
  const out = new Map<string, EnvCellRow>();
  for (const c of m.cells || []) {
    out.set(`${c.requirement}${SEP}${c.environment}`, c);
  }
  return out;
}

export function cellKey(requirement: string, environment: string): string {
  return `${requirement}${SEP}${environment}`;
}

/** pendingByEnvironment — {env: cuántas celdas "falta"}. Puro. */
export function pendingByEnvironment(m: EnvMatrixResponse): Record<string, number> {
  const out: Record<string, number> = {};
  for (const env of m.environments || []) out[env] = 0;
  for (const c of m.cells || []) {
    if (c.state !== 'falta') continue;
    out[c.environment] = (out[c.environment] || 0) + 1;
  }
  return out;
}

/** headline — el titular único. Es, literalmente, todo el trabajo que le queda. */
export function headline(m: EnvMatrixResponse): string {
  const n = m?.pending_count ?? 0;
  if (n === 0) return 'No falta nada: esta pipeline tiene todo lo que necesita.';
  if (n === 1) return 'Te falta 1 valor para que esta pipeline pueda correr.';
  return `Te faltan ${n} valores para que esta pipeline pueda correr.`;
}

const ORDEN_ESTADO: Record<CellState, number> = {
  falta: 0,
  default: 1,
  manual: 2,
  definido: 3,
};

/** sortRequirements — primero lo que falta. INMUTABLE: no toca el array de entrada. */
export function sortRequirements(m: EnvMatrixResponse): EnvRequirement[] {
  const peor = new Map<string, number>();
  for (const c of m.cells || []) {
    const actual = peor.get(c.requirement);
    const rank = ORDEN_ESTADO[c.state] ?? 9;
    if (actual === undefined || rank < actual) peor.set(c.requirement, rank);
  }
  return [...(m.requirements || [])].sort((a, b) => {
    const ra = peor.get(a.name) ?? 9;
    const rb = peor.get(b.name) ?? 9;
    if (ra !== rb) return ra - rb;
    return a.name.localeCompare(b.name);
  });
}

/** canCompleteInStacky — sólo `variable` y `secret` se cargan por API en v1.
 *  `server` va a la sección Servidores; `service_connection` y `deploy_path` son
 *  manuales y quedan documentados en el paquete del plan 252. */
export function canCompleteInStacky(r: EnvRequirement): boolean {
  return r.kind === 'variable' || r.kind === 'secret';
}

/** C12 — leer el inventario del plan 246 SIN romper `tsc --noEmit` cuando ese plan
 *  no está mergeado. `DevOpsSectionContext` es una interfaz CERRADA: el acceso
 *  directo a un campo inexistente es un error de compilación, no un `undefined`. */
type WithInventory = {
  pipelineInventory?: Array<{ id: string; name: string; yaml_path: string }>;
};

export function readInventory(ctx: unknown): WithInventory['pipelineInventory'] {
  const c = ctx as WithInventory | null | undefined;
  return Array.isArray(c?.pipelineInventory) ? c!.pipelineInventory : undefined;
}

/** Comparación de huellas entre dos análisis: ¿bajó el trabajo pendiente? */
export function pendingDelta(
  actual: EnvMatrixResponse,
  anterior: { fingerprint: string; pending: number } | null,
): string {
  if (!anterior || !anterior.fingerprint) return '';
  if (anterior.fingerprint === actual.pending_fingerprint) return 'sin cambios desde el último análisis';
  if (actual.pending_count < anterior.pending) {
    return `bajó de ${anterior.pending} a ${actual.pending_count}`;
  }
  if (actual.pending_count > anterior.pending) {
    return `subió de ${anterior.pending} a ${actual.pending_count}`;
  }
  return 'cambió lo que falta, pero siguen siendo los mismos';
}
