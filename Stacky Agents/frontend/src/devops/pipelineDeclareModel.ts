/** Plan 260 F6 — modelo PURO de la declaración de nombres. Sin React, sin fetch,
 *  sin DOM. Tipos espejo de services/pipeline_env_declare.py (DeclareItem/DeclarePlan). */

export interface DeclareItemView {
  key: string;
  secret: boolean;
  reason: string;
  note: string;
}

export interface DeclarePlanView {
  items: DeclareItemView[];
  skipped: Array<{ key: string; motivo: string }>;
  provider: string;
}

/** resumenDeclaracion — "Stacky va a crear N nombres; vos solo pegás los valores". */
export function resumenDeclaracion(plan: DeclarePlanView): string {
  const n = plan.items.length;
  if (n === 0) {
    return 'No hay nombres nuevos para declarar en este momento.';
  }
  if (n === 1) {
    return 'Stacky va a crear 1 nombre; vos solo pegás el valor.';
  }
  return `Stacky va a crear ${n} nombres; vos solo pegás los valores.`;
}

/** agruparSkipped — motivo -> lista de keys, mismo orden de llegada. */
export function agruparSkipped(plan: DeclarePlanView): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const { key, motivo } of plan.skipped || []) {
    const lista = out.get(motivo) || [];
    lista.push(key);
    out.set(motivo, lista);
  }
  return out;
}

/** (v2, ADICIÓN 3) avisoContadorNoBaja — el texto que explica que la alerta
 *  NO va a bajar al declarar, y por qué eso es correcto (KPI-2). Si el
 *  proyectado fuera MENOR al actual, es el canario de que el bug de §2.3/§2.5
 *  volvió: se lo dice explícitamente en vez de quedar en silencio. */
export function avisoContadorNoBaja(actual: number, proyectado: number): string {
  if (proyectado === actual) {
    return (
      `Declarar estos nombres no baja el contador de pendientes (sigue en ${actual}): ` +
      'vas a poder cargar el valor real después, y recién ahí deja de figurar como pendiente.'
    );
  }
  return (
    `Ojo: se esperaba que el pendiente no bajara y pasó de ${actual} a ${proyectado}. ` +
    'Volvé a analizar la pipeline antes de confiar en este número.'
  );
}

/** (v2, C6) avisoMasking — keys que quedaron con masked=false tras declarar. */
export function avisoMasking(needsMasking: string[]): string {
  if (!needsMasking || needsMasking.length === 0) return '';
  return (
    `Estas ${needsMasking.length} quedaron sin enmascarar: marcá 'secreta' al cargar el valor ` +
    `o GitLab lo va a imprimir en el log del job (${needsMasking.join(', ')}).`
  );
}
