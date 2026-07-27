/**
 * previewFetcher.ts — Plan 99 F0.
 *
 * Corazón del preview YAML: cache por spec + anti-stale + errores estructurados.
 * Módulo PURO (sin React, sin timers, sin globals) para que toda la lógica con
 * estados y carreras sea testeable de forma determinista — en este repo
 * `@testing-library/react` y `jsdom` NO están instalados, así que lo que no viva
 * acá afuera no se puede probar.
 *
 * Contrato anti-race IDÉNTICO al de components/devops/PipelineLintPanel.tsx:50,95,101
 * (secuencia monótona + descarte del superado). El AbortController es cinturón 2:
 * ahorra red, pero la corrección NO depende de él.
 */
import { isAbortError } from '../api/client';

export interface PreviewData {
  ado: string;
  gitlab: string;
}

export interface PreviewFieldError {
  field: string;
  message: string;
}

/**
 * Desenlace de un pedido. `stale` es un no-evento: el caller NO debe tocar
 * ningún estado (ni siquiera apagar el loading), porque hay un pedido más nuevo
 * en vuelo que se encargará del desenlace.
 */
export type PreviewOutcome =
  | { kind: 'ok'; data: PreviewData }
  | { kind: 'error'; errors: PreviewFieldError[] }
  | { kind: 'stale' };

export const PREVIEW_CACHE_LIMIT = 20;

/**
 * Convierte el error que tira `api.post` en errores por campo.
 *
 * `api/client.ts:155` tira SIEMPRE un `Error` plano con la forma
 * `"<status> <statusText>: <body>"`. Un `Error` plano NUNCA tiene la key
 * `errors`, así que el branch `'errors' in e` del código viejo
 * (PipelineYamlPreview.tsx:75) era inalcanzable: los 400 estructurados del
 * backend se mostraban como un chorizo. Acá se parsea el body de verdad.
 */
export function parsePreviewError(e: unknown): PreviewFieldError[] {
  const generico = (msg: string): PreviewFieldError[] => [{ field: 'general', message: msg }];
  if (!(e instanceof Error)) return generico('Error desconocido');

  // Caso raro pero legítimo: alguien nos pasa un objeto ya estructurado.
  const conErrors = e as unknown as { errors?: unknown };
  if (Array.isArray(conErrors.errors)) {
    return conErrors.errors as PreviewFieldError[];
  }

  const msg = e.message;
  const inicio = msg.indexOf('{');
  if (inicio === -1) return generico(msg);
  try {
    const body = JSON.parse(msg.slice(inicio)) as { errors?: unknown };
    if (Array.isArray(body.errors) && body.errors.length > 0) {
      return (body.errors as unknown[]).map((raw) => {
        const it = (raw ?? {}) as { field?: unknown; message?: unknown };
        return {
          field: typeof it.field === 'string' ? it.field : '',
          message: typeof it.message === 'string' ? it.message : String(raw),
        };
      });
    }
  } catch {
    // C8 — el slice pudo cortar en un '{' que no abría JSON. Degradar al mensaje
    // plano es exactamente lo correcto: nunca peor que el comportamiento viejo.
  }
  return generico(msg);
}

export interface PreviewFetcher {
  /** Pide el preview del spec. Cachea los éxitos; descarta los desenlaces superados. */
  request: (spec: object) => Promise<PreviewOutcome>;
  /** Vacía el cache (lo usa el botón manual "Actualizar preview"). */
  invalidate: () => void;
  /** Solo para tests/diagnóstico. */
  cacheSize: () => number;
}

type PreviewCall = (spec: object, signal: AbortSignal) => Promise<PreviewData>;

/**
 * Crea un fetcher con cache LRU por serialización canónica del spec.
 *
 * La key es `JSON.stringify(spec)`: todos los specs nacen de `toSpecDict`
 * (mismo código, mismo orden de propiedades), así que el peor caso teórico de
 * un orden distinto es un cache miss inofensivo, nunca un dato incorrecto.
 */
export function createPreviewFetcher(call: PreviewCall): PreviewFetcher {
  const cache = new Map<string, PreviewData>();
  let seq = 0;
  let enVuelo: AbortController | null = null;

  const recordar = (key: string, data: PreviewData) => {
    // Map preserva orden de inserción ⇒ el primer key es el menos usado.
    if (cache.has(key)) cache.delete(key);
    cache.set(key, data);
    while (cache.size > PREVIEW_CACHE_LIMIT) {
      const viejo = cache.keys().next();
      if (viejo.done) break;
      cache.delete(viejo.value);
    }
  };

  return {
    request: async (spec: object): Promise<PreviewOutcome> => {
      const key = JSON.stringify(spec);
      const mySeq = ++seq;

      const hit = cache.get(key);
      if (hit !== undefined) {
        // Refrescar el orden LRU aunque no se pegue a la red.
        recordar(key, hit);
        // Un hit también puede quedar superado: si mientras tanto salió un
        // pedido más nuevo, este desenlace no debe pisar nada.
        if (mySeq !== seq) return { kind: 'stale' };
        return { kind: 'ok', data: hit };
      }

      // Cinturón 2: cancelar el pedido anterior ahorra red. La corrección la da
      // la secuencia, no esto.
      if (enVuelo) enVuelo.abort();
      const controller = new AbortController();
      enVuelo = controller;

      try {
        const data = await call(spec, controller.signal);
        if (mySeq !== seq) return { kind: 'stale' };
        recordar(key, data);
        return { kind: 'ok', data };
      } catch (e: unknown) {
        if (mySeq !== seq) return { kind: 'stale' };
        if (isAbortError(e)) return { kind: 'stale' };
        return { kind: 'error', errors: parsePreviewError(e) };
      } finally {
        if (enVuelo === controller) enVuelo = null;
      }
    },
    invalidate: () => {
      cache.clear();
    },
    cacheSize: () => cache.size,
  };
}
