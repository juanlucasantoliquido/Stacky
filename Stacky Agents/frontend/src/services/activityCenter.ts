/**
 * Plan 152 F1 — Centro de Actividad: store singleton + pub/sub + persistencia.
 *
 * Estado vivo compartido (variable de módulo, mismo patrón que tabTitle.ts /
 * executionNotifier.ts) sobre el reducer puro. Único punto donde las fuentes
 * ESCRIBEN (publishActivity) y la UI LEE (subscribeActivity + snapshot).
 *
 * El único mecanismo de refresco del feed es react-query aguas arriba (la query
 * compartida de runs) y las llamadas directas de las fuentes a publishActivity;
 * este módulo NO abre canales de red ni temporizadores propios.
 */
import {
  appendEvent,
  emptyState,
  hydrateState,
  isMuted,
  LS_STATE_KEY,
  markAllRead,
  serializeState,
  setMuted,
  type ActivityEvent,
  type ActivityKind,
  type ActivityState,
} from "./activityReducer";

interface StorageLike {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
  removeItem(k: string): void;
}

/** Devuelve el storage del entorno o null (node de vitest, modo privado). */
function storage(): StorageLike | null {
  try {
    const ls = (globalThis as { localStorage?: StorageLike }).localStorage;
    return ls ?? null;
  } catch {
    return null;
  }
}

function safeGet(key: string): string | null {
  const ls = storage();
  if (!ls) return null;
  try {
    return ls.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, val: string): void {
  const ls = storage();
  if (!ls) return;
  try {
    ls.setItem(key, val);
  } catch {
    /* cuota llena / modo privado: degradación silenciosa, nunca lanza */
  }
}

function safeRemove(key: string): void {
  const ls = storage();
  if (!ls) return;
  try {
    ls.removeItem(key);
  } catch {
    /* ignorar */
  }
}

let state: ActivityState | null = null;
const subscribers = new Set<() => void>();

/** Hidrata perezosamente al primer acceso; luego devuelve la referencia viva. */
function ensure(): ActivityState {
  if (state == null) state = hydrateState(safeGet(LS_STATE_KEY));
  return state;
}

/** Reemplaza el estado (nueva referencia), persiste y notifica a los suscriptores. */
function commit(next: ActivityState): void {
  state = next;
  safeSet(LS_STATE_KEY, serializeState(next));
  for (const cb of subscribers) cb();
}

/** Fuente → store. Si el kind está silenciado, descarta (no guarda, no notifica). */
export function publishActivity(e: ActivityEvent): void {
  const cur = ensure();
  if (isMuted(cur, e.kind)) return;
  commit(appendEvent(cur, e));
}

export function subscribeActivity(cb: () => void): () => void {
  subscribers.add(cb);
  return () => {
    subscribers.delete(cb);
  };
}

/**
 * Referencia ESTABLE entre cambios (requisito de useSyncExternalStore para no
 * loopear): solo se reemplaza en commit().
 */
export function getActivitySnapshot(): ActivityState {
  return ensure();
}

export function markActivityRead(): void {
  commit(markAllRead(ensure(), Date.now()));
}

export function getMuted(): ActivityKind[] {
  return ensure().muted;
}

export function setActivityMuted(kind: ActivityKind, on: boolean): void {
  commit(setMuted(ensure(), kind, on));
}

/** Solo tests: limpia estado en memoria + storage + suscriptores. */
export function __resetActivityForTests(): void {
  state = emptyState();
  subscribers.clear();
  safeRemove(LS_STATE_KEY);
}
