/**
 * capabilityDegradedModel.ts — Plan 290 F4.
 *
 * Lógica PURA de lectura de `metadata.capability_degraded`: la lista de
 * capacidades que Stacky decidió A PROPÓSITO no ejecutar porque el tracker del
 * proyecto no las tiene. No es una lista de errores.
 *
 * Va en `.ts` puro y no en el `.tsx` porque RTL/jsdom no están instalados en este
 * repo: un `.test.tsx` con RTL reporta "no tests" y sale con exit 0 — un falso
 * verde perfecto. `vitest` sobre `.ts` sí corre, y este archivo es lo que se
 * testea; el componente solo pinta.
 */

/** Forma canónica que escribe `services/capability_degradation.py`. Cinco claves
 *  y ninguna más: el contrato está congelado del lado del backend. */
export interface DegradacionDeclarada {
  capability: string;
  reason: string;
  provider: string;
  site: string;
  at: string;
}

/**
 * Etiquetas legibles de las capacidades que este plan emite.
 *
 * Las DOS keys de producción están acá y ninguna cae al default: el operador
 * siempre lee castellano. Es un diccionario DISTINTO de `CAPABILITY_MATRIX` del
 * backend — que `tracker.acceptance_criteria` no esté en aquella (por §F3.2) no
 * implica que no esté en esta.
 */
const ETIQUETAS: Record<string, string> = {
  "tracker.comments.list": "Lectura de comentarios del tracker",
  "tracker.acceptance_criteria": "Criterios de aceptación",
};

function esEntradaValida(x: unknown): x is DegradacionDeclarada {
  if (typeof x !== "object" || x === null) return false;
  const e = x as Record<string, unknown>;
  return typeof e.capability === "string" && e.capability.length > 0;
}

/**
 * Lee `metadata.capability_degraded` de forma DEFENSIVA. Nunca lanza.
 *
 * Una metadata sin la clave, con la clave en `null`, o con un valor que no es
 * array, devuelve `[]`. Las entradas que no son objeto se descartan de a una: una
 * entrada corrupta no puede vaciar la lista entera.
 */
export function leerDegradaciones(
  metadata: Record<string, unknown> | null | undefined,
): DegradacionDeclarada[] {
  if (!metadata || typeof metadata !== "object") return [];
  const bruto = (metadata as Record<string, unknown>).capability_degraded;
  if (!Array.isArray(bruto)) return [];
  return bruto.filter(esEntradaValida).map((e) => ({
    capability: e.capability,
    reason: typeof e.reason === "string" ? e.reason : "",
    provider: typeof e.provider === "string" ? e.provider : "",
    site: typeof e.site === "string" ? e.site : "",
    at: typeof e.at === "string" ? e.at : "",
  }));
}

/**
 * Etiqueta legible. Una capacidad DESCONOCIDA devuelve la key cruda, NUNCA
 * `undefined` ni `""` — mismo criterio que `statusLabel` de `parityMatrixModel`.
 *
 * El `??` y NO `||` es deliberado: con `||`, una key `""` caería al default y
 * React renderizaría vacío, dejando el aviso mudo — el defecto que este plan
 * viene a arreglar, reintroducido una capa más arriba.
 *
 * Este default es un BORDE DEFENSIVO para el día en que alguien instrumente un
 * noveno sitio y se olvide la etiqueta, no el camino normal.
 */
export function etiquetaDeCapacidad(capability: string): string {
  return ETIQUETAS[capability] ?? capability;
}

/** Agrupa por proveedor preservando el orden de llegada (el de escritura). */
export function agruparPorProveedor(
  items: DegradacionDeclarada[],
): Array<[string, DegradacionDeclarada[]]> {
  const orden: string[] = [];
  const mapa = new Map<string, DegradacionDeclarada[]>();
  for (const it of items) {
    const clave = it.provider || "desconocido";
    if (!mapa.has(clave)) {
      mapa.set(clave, []);
      orden.push(clave);
    }
    mapa.get(clave)!.push(it);
  }
  return orden.map((k) => [k, mapa.get(k)!] as [string, DegradacionDeclarada[]]);
}
