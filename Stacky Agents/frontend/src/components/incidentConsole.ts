// Plan 200 F2 — Consola del agente dentro del detalle de la incidencia.
//
// Hoy el transcript de una ejecución vive en otra pantalla: para entender qué
// hizo el agente con una incidencia hay que salir del detalle y buscarla por id.
// Estos helpers son puros para poder testearlos sin DOM (el repo no tiene RTL).

export interface IncidentExecRef {
  execution_id: number;
  kind: string;
  linked_at: string | null;
}

export interface ConsoleResponse {
  ok: boolean;
  executions: IncidentExecRef[];
  primary_execution_id: number | null;
}

const ETIQUETAS: Record<string, string> = {
  analysis: "Analisis",
  dev_resolver: "Dev-resolutor",
};

/** El kind desconocido se muestra crudo: una etiqueta fea es mejor que una fila
 *  que no aparece porque nadie previó ese tipo de ejecución. */
export function execLabel(e: IncidentExecRef): string {
  return `#${e.execution_id} · ${ETIQUETAS[e.kind] ?? e.kind}`;
}

/** Prioridad de lectura, no alfabética: el análisis explica por qué existe todo
 *  lo demás, así que va primero. */
const ORDEN_KIND = ["analysis", "dev_resolver"];

function rankKind(kind: string): number {
  const i = ORDEN_KIND.indexOf(kind);
  return i === -1 ? ORDEN_KIND.length : i;
}

export function orderExecs(execs: IncidentExecRef[]): IncidentExecRef[] {
  return [...(execs ?? [])].sort((a, b) => {
    const ra = rankKind(a.kind);
    const rb = rankKind(b.kind);
    if (ra !== rb) return ra - rb;
    // Empate entre dos kinds desconocidos: por nombre, para que el orden no
    // dependa de cómo vino el array.
    if (ra === ORDEN_KIND.length && a.kind !== b.kind) return a.kind.localeCompare(b.kind);
    return a.execution_id - b.execution_id;
  });
}

/** Una línea del log. Los campos faltantes se omiten en vez de imprimirse como
 *  "undefined": basta un par de esos para desconfiar del transcript entero. */
export function logLineText(ev: {
  timestamp?: string;
  level?: string;
  message?: string;
}): string {
  return [ev?.timestamp, ev?.level ? `[${ev.level}]` : "", ev?.message]
    .filter((p) => Boolean(p))
    .join(" ");
}
