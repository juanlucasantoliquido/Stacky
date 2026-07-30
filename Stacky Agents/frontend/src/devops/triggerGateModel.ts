/** Plan 260 F6 — modelo PURO del veredicto de disparo. Sin React, sin fetch,
 *  sin DOM. Tipo espejo de services/ci_env_gate.py (Readiness). */

export type ReadinessVerdict = 'ok' | 'bloquea' | 'advierte' | 'degradado';

export interface ReadinessView {
  verdict: ReadinessVerdict;
  pending_count: number;
  unknown_count: number;
  missing: Array<{ name: string; environment: string }>;
  elapsed_ms: number;
  resolved: boolean;
  source: string;
}

/** mensajeDeBloqueo — lista NOMBRES, jamás valores (KPI-5). */
export function mensajeDeBloqueo(readiness: ReadinessView): string {
  const nombres = [...new Set((readiness.missing || []).map((m) => m.name))];
  if (nombres.length === 0) {
    return 'No podés disparar: faltan valores obligatorios para esta pipeline.';
  }
  if (nombres.length === 1) {
    return `No podés disparar: falta 1 valor (${nombres[0]}).`;
  }
  return `No podés disparar: faltan ${nombres.length} valores (${nombres.join(', ')}).`;
}

/** puedeDisparar — el gate NUNCA bloquea por ignorancia (§3.4): solo
 *  'bloquea' exige ack explícito; 'degradado'/'advierte'/'ok' siempre dejan pasar. */
export function puedeDisparar(readiness: ReadinessView, ack: boolean): boolean {
  if (readiness.verdict === 'bloquea') return ack === true;
  return true;
}

/** avisoAdvertencia — 'advierte': el proveedor no puede confirmar, pero no bloquea. */
export function avisoAdvertencia(readiness: ReadinessView): string {
  const n = readiness.unknown_count;
  return (
    `Stacky no puede confirmar ${n} valor(es) obligatorio(s) (el proveedor no lo informa). ` +
    'Podés disparar igual, pero conviene verificarlos vos.'
  );
}

/** (ADICIÓN 5) mensajeDegradado — convierte "degradado" en algo accionable:
 *  un elapsed_ms alto dice "tu proveedor está lento"; uno bajo dice "no pude
 *  obtener el YAML". Nunca bloquea (source de verdad: puedeDisparar). */
export function mensajeDegradado(readiness: ReadinessView): string {
  if (readiness.elapsed_ms > 1500) {
    return (
      `No se pudo verificar a tiempo (esperamos ${readiness.elapsed_ms} ms): el disparo sigue ` +
      'habilitado, pero no hay certeza de que no falten valores.'
    );
  }
  return 'No se pudo verificar si faltan valores obligatorios: el disparo sigue habilitado.';
}
