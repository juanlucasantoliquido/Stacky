/**
 * services/parityMatrixModel.ts — Plan 218 F8.
 *
 * Lógica PURA del panel de paridad: agrupación por dominio, resumen por estado y
 * etiquetas legibles. Sin React, sin fetch, sin estado — así se testea con vitest
 * sin jsdom (el frontend no tiene jsdom ni @testing-library).
 */

export type CapabilityStatus = 'full' | 'partial' | 'absent' | 'n/a';

export interface CapabilityRow {
  key: string;
  status: CapabilityStatus | string;
  enabled: boolean;
  loss: string;
  owner_plan: number | null;
}

export interface ParityMatrixResponse {
  provider: string;
  project: string;
  parity_enabled: boolean;
  capabilities: CapabilityRow[];
}

export interface StatusSummary {
  full: number;
  partial: number;
  absent: number;
  na: number;
}

/** Dominio = el prefijo antes del primer punto (`mr.approve` → `mr`). */
export function domainOf(key: string): string {
  const i = key.indexOf('.');
  return i === -1 ? key : key.slice(0, i);
}

/** Agrupa preservando el orden de llegada (el registro ya viene ordenado). */
export function groupByDomain(caps: CapabilityRow[]): Array<[string, CapabilityRow[]]> {
  const orden: string[] = [];
  const porDominio = new Map<string, CapabilityRow[]>();
  for (const cap of caps ?? []) {
    const dom = domainOf(cap.key);
    if (!porDominio.has(dom)) {
      porDominio.set(dom, []);
      orden.push(dom);
    }
    porDominio.get(dom)!.push(cap);
  }
  return orden.map((dom) => [dom, porDominio.get(dom)!]);
}

export function summarize(caps: CapabilityRow[]): StatusSummary {
  const out: StatusSummary = { full: 0, partial: 0, absent: 0, na: 0 };
  for (const cap of caps ?? []) {
    if (cap.status === 'full') out.full += 1;
    else if (cap.status === 'partial') out.partial += 1;
    else if (cap.status === 'n/a') out.na += 1;
    else out.absent += 1;
  }
  return out;
}

/** Etiqueta humana. Nunca devuelve undefined: lo desconocido cae en "ausente". */
export function statusLabel(status: string): string {
  switch (status) {
    case 'full':
      return 'Completa';
    case 'partial':
      return 'Parcial';
    case 'n/a':
      return 'No aplica';
    default:
      return 'Ausente';
  }
}

/**
 * Marca NO cromática por estado: el color solo no puede ser el único portador de
 * información (accesibilidad; y el ratchet de UI prohíbe hex crudos).
 */
export function statusMark(status: string): string {
  switch (status) {
    case 'full':
      return '✓';
    case 'partial':
      return '~';
    case 'n/a':
      return '—';
    default:
      return '✕';
  }
}
