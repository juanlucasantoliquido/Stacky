/** Plan 246 F5 — modelo puro del inventario de pipelines. Sin DOM, sin React, sin fetch.
 *  Los tipos son el ESPEJO del contrato congelado de services/pipeline_inventory.py (F0). */

export type InventoryCategory =
  | 'registrada+en_repo'
  | 'registrada_sin_archivo'
  | 'en_repo_sin_registrar'
  | 'registrada_estado_desconocido'; // [v2 — C2] barrido no confiable: NUNCA en rojo

export type RunStatus = 'success' | 'failed' | 'never_ran' | 'unknown';

export type Tone = 'ok' | 'bad' | 'faint' | 'warn';

export interface InventoryLastRun {
  status: RunStatus;
  status_detail: string;
  at: string | null;
  web_url: string | null;
  run_id: string | null;
  source: string | null;
}

export interface InventoryTrigger {
  kind: string;
  branches: string[];
  has_paths: boolean;
  has_schedule: boolean;
  has_pr: boolean;
  source: string | null;
}

export interface InventoryEntry {
  key: string;
  provider: string;
  name: string;
  yaml_path: string | null;
  default_branch: string | null;
  definition_id: string | null;
  category: InventoryCategory;
  category_reason: string;
  last_run: InventoryLastRun;
  trigger: InventoryTrigger;
  found_in: string[];
  hints: string[]; // [ADICIÓN ARQUITECTO v2] rutas parecidas; [] cuando no aplica
}

export interface InventorySource {
  id: string;
  available: boolean;
  count: number;
  capability: string;
  provider: string;
  reason: string;
  workaround: string;
  // [v2 — C6] extras opcionales de truncación (source_ok(**extra)):
  capped?: boolean;
  hydrated?: number;
  truncated_hydration?: boolean;
  truncated?: boolean;
  skipped_too_big?: number;
  skipped_unparseable?: number;
  scanned_files?: number;
}

export interface InventoryPayload {
  ok: boolean;
  generated_at: string;
  cached: boolean;
  cache_age_sec: number;
  project: string;
  counts: Record<string, number>;
  sources: InventorySource[];
  pipelines: InventoryEntry[];
}

export const INVENTORY_CATEGORIES: InventoryCategory[] = [
  'registrada_sin_archivo',
  'en_repo_sin_registrar',
  'registrada+en_repo',
  'registrada_estado_desconocido',
];

/** Etiqueta en castellano + tono para la UI. Tabla CERRADA, sin default silencioso. */
export function statusLabel(r: InventoryLastRun): { text: string; tone: Tone } {
  switch (r.status) {
    case 'success':
      return { text: 'Verde', tone: 'ok' };
    case 'failed':
      return { text: 'Rojo', tone: 'bad' };
    case 'never_ran':
      return { text: 'Nunca corrio', tone: 'faint' };
    default: {
      const detalle = (r.status_detail || '').trim();
      const sufijo = detalle && detalle !== 'sin_datos' ? ` (${detalle})` : '';
      return { text: `Desconocido${sufijo}`, tone: 'warn' };
    }
  }
}

/** Etiqueta + explicacion de cada categoria. Tabla CERRADA de 4 filas. [v2 — C2] */
export function categoryLabel(c: InventoryCategory): { text: string; hint: string; tone: Tone } {
  switch (c) {
    case 'registrada+en_repo':
      return {
        text: 'Registrada',
        hint: 'Registrada en el proveedor y con su YAML en el repo.',
        tone: 'ok',
      };
    case 'registrada_sin_archivo':
      return {
        text: 'Sin archivo',
        hint: 'Registrada en el proveedor pero su YAML no esta en el repo.',
        tone: 'bad',
      };
    case 'en_repo_sin_registrar':
      return {
        text: 'Huerfana',
        hint: 'El YAML esta en el repo pero no esta registrada en ningun proveedor.',
        tone: 'warn',
      };
    default:
      return {
        text: 'Sin verificar',
        hint:
          'Registrada en el proveedor. No se pudo revisar el repo, asi que no se afirma si el archivo esta o no.',
        tone: 'faint',
      };
  }
}

/** Texto del trigger en una linea, deterministico. Nunca inventa: 'unknown' -> 'Sin datos'. */
export function triggerLabel(t: InventoryTrigger): string {
  let base: string;
  switch (t.kind) {
    case 'default':
      base = 'Toda rama (sin bloque trigger)';
      break;
    case 'none':
      base = 'Manual (trigger: none)';
      break;
    case 'ci':
      base = `CI: ${t.branches.length ? t.branches.join(', ') : 'sin ramas declaradas'}`;
      if (t.has_paths) base += ' [filtra paths]';
      break;
    default:
      base = 'Sin datos';
      break;
  }
  if (t.has_schedule) base += ' + programado';
  if (t.has_pr) base += ' + PR';
  return base;
}

/** Agrupa por categoria conservando el orden del backend dentro de cada grupo. */
export function groupByCategory(
  entries: InventoryEntry[],
): Record<InventoryCategory, InventoryEntry[]> {
  const out = {} as Record<InventoryCategory, InventoryEntry[]>;
  INVENTORY_CATEGORIES.forEach((c) => {
    out[c] = [];
  });
  entries.forEach((e) => {
    if (!out[e.category]) out[e.category] = [];
    out[e.category].push(e);
  });
  return out;
}

/** Filtro de texto: match case-insensitive sobre name, yaml_path y provider. '' => todo. */
export function filterEntries(entries: InventoryEntry[], q: string): InventoryEntry[] {
  const needle = (q || '').trim().toLowerCase();
  if (!needle) return entries;
  return entries.filter((e) =>
    [e.name, e.yaml_path || '', e.provider].some((campo) =>
      campo.toLowerCase().includes(needle),
    ),
  );
}

/** Linea de resumen del header. Nunca devuelve ''. */
export function summarize(p: InventoryPayload | null): string {
  if (!p) return 'Todavia no se consulto el inventario.';
  const total = p.counts?.total ?? 0;
  if (!total) return 'Sin pipelines descubiertas';
  const rotas = p.counts?.['registrada_sin_archivo'] ?? 0;
  const huerfanas = p.counts?.['en_repo_sin_registrar'] ?? 0;
  return `${total} pipelines · ${rotas} sin archivo · ${huerfanas} huerfanas`;
}

/** Fuentes caidas, para el banner honesto. [] si todas estan bien. */
export function unavailableSources(p: InventoryPayload | null): InventorySource[] {
  if (!p || !Array.isArray(p.sources)) return [];
  return p.sources.filter((s) => s && s.available === false);
}

/** [v2 — C6] Avisos de TRUNCACION, uno por condicion, en castellano. [] si no hubo recorte.
 *  Un inventario que recorta y no lo dice es un inventario que miente. */
export function truncationNotices(p: InventoryPayload | null): string[] {
  if (!p || !Array.isArray(p.sources)) return [];
  const out: string[] = [];
  const any = (pred: (s: InventorySource) => boolean) => p.sources.some((s) => !!s && pred(s));
  const sum = (pick: (s: InventorySource) => number | undefined) =>
    p.sources.reduce((acc, s) => acc + (s && pick(s) ? (pick(s) as number) : 0), 0);

  if (any((s) => !!s.capped)) {
    out.push('Se listaron solo las primeras 50 definiciones del proveedor.');
  }
  if (any((s) => !!s.truncated_hydration)) {
    out.push(
      'Algunas definiciones quedaron sin ruta de YAML (limite de 10 consultas de detalle).',
    );
  }
  if (any((s) => !!s.truncated)) {
    out.push(
      'El barrido del repositorio se corto en 400 archivos: puede faltar alguna pipeline.',
    );
  }
  const gordos = sum((s) => s.skipped_too_big);
  if (gordos > 0) out.push(`${gordos} archivo(s) YAML se saltaron por superar 512 KB.`);
  const ilegibles = sum((s) => s.skipped_unparseable);
  if (ilegibles > 0) out.push(`${ilegibles} archivo(s) YAML no se pudieron leer.`);
  return out;
}

/** [ADICION ARQUITECTO v2] Pista de por que una entrada no reconcilio. '' si no aplica.
 *  NO propone accion automatica: es informacion para que decida el operador. */
export function mismatchHint(entry: InventoryEntry): string {
  const hints = entry.hints || [];
  if (!hints.length) return '';
  if (entry.category === 'registrada_sin_archivo') {
    return `En el repo hay rutas parecidas: ${hints.join(', ')}. Puede ser un renombre.`;
  }
  if (entry.category === 'en_repo_sin_registrar') {
    return `Hay definiciones registradas con rutas parecidas: ${hints.join(', ')}.`;
  }
  return '';
}

/** Mensaje del estado vacio, DISCRIMINANDO la causa (no un 'no hay nada' mudo). */
export function emptyStateMessage(p: InventoryPayload | null, filtered: number): string {
  if (!p) return 'Todavia no se consulto el inventario.';
  const caidas = unavailableSources(p);
  if (caidas.length && caidas.length === (p.sources || []).length) {
    return 'No se pudo consultar ninguna fuente. Mira el detalle de abajo.';
  }
  if ((p.pipelines || []).length === 0) {
    return 'No hay pipelines en este proyecto (ni registradas ni en el repo).';
  }
  if (filtered === 0) return 'Ninguna pipeline coincide con el filtro.';
  return '';
}
