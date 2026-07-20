/**
 * undoManager.ts — Plan 185 F1. Núcleo PURO (sin React) del patrón undo universal.
 *
 * Agenda acciones reversibles con una gracia corta; garantiza commit-o-undo
 * exactamente-una-vez; serializa los commits de un MISMO id en orden de despacho
 * (C3, cadena de promesas por id); notifica a la UI vía subscribe().
 *
 * Inerte hasta que alguien lo llame. La flag STACKY_UNDO_UNIVERSAL_ENABLED se
 * cablea vía setBypass() en UndoToastHost (flag OFF ⇒ bypass: commit inmediato).
 */

export const DEFAULT_GRACE_MS = 6000; // clamp duro [2000, 15000]
const MIN_GRACE_MS = 2000;
const MAX_GRACE_MS = 15000;

export type FlushReason = "expired" | "pagehide" | "replaced" | "manual";

export interface UndoableSpec {
  id: string; // único por acción lógica, formato "<dominio>:<id-entidad>"
  label: string; // texto humano del toast, ej: "Ticket archivado"
  graceMs?: number; // default DEFAULT_GRACE_MS, clampeado a [2000, 15000]
  commit: () => void | Promise<void>; // efecto real (llamada API)
  onUndo?: () => void; // revertir la mutación optimista de UI
  onCommitted?: () => void;
  onError?: (e: unknown) => void; // commit rechazado/lanzó
}

export interface PendingUndoable {
  id: string;
  label: string;
  createdAt: number;
  expiresAt: number;
}

interface Entry {
  spec: UndoableSpec;
  createdAt: number;
  expiresAt: number;
  timer: ReturnType<typeof setTimeout>;
}

// Estado interno a nivel módulo (singleton del dashboard).
const entries = new Map<string, Entry>();
// Cadena de promesas por id: TODO commit del mismo id se encadena (C3).
const commitChains = new Map<string, Promise<void>>();
const listeners = new Set<() => void>();
let bypass = false;

function clampGrace(ms: number | undefined): number {
  const v = ms ?? DEFAULT_GRACE_MS;
  if (!Number.isFinite(v)) return DEFAULT_GRACE_MS;
  return Math.min(MAX_GRACE_MS, Math.max(MIN_GRACE_MS, v));
}

function notify(): void {
  for (const l of Array.from(listeners)) l();
}

/**
 * Despacha el commit de una spec por la cadena de promesas de su id.
 * Commits de ids distintos corren en paralelo; del mismo id, en orden de despacho.
 */
function dispatchCommit(spec: UndoableSpec): void {
  const prev = commitChains.get(spec.id) ?? Promise.resolve();
  const next = prev.then(
    () => spec.commit(),
  ).then(
    () => {
      spec.onCommitted?.();
    },
    (e) => {
      spec.onError?.(e);
    },
  );
  // La cadena guardada nunca rechaza (para no romper commits posteriores del id).
  commitChains.set(
    spec.id,
    next.then(
      () => {},
      () => {},
    ),
  );
}

function removeEntry(id: string): Entry | undefined {
  const e = entries.get(id);
  if (e) {
    clearTimeout(e.timer);
    entries.delete(id);
  }
  return e;
}

/** true = flag OFF: commit inmediato (por la misma cadena por id), sin toast, sin notificar. */
export function setBypass(b: boolean): void {
  bypass = b;
}

export function scheduleUndoable(spec: UndoableSpec): void {
  if (bypass) {
    dispatchCommit(spec);
    return;
  }
  // (1) id ya pendiente ⇒ flush del anterior con reason "replaced", luego agenda.
  const existing = removeEntry(spec.id);
  if (existing) {
    dispatchCommit(existing.spec);
  }
  const graceMs = clampGrace(spec.graceMs);
  const createdAt = Date.now();
  const expiresAt = createdAt + graceMs;
  const timer = setTimeout(() => {
    const cur = entries.get(spec.id);
    if (cur && cur.timer === timer) {
      entries.delete(spec.id);
      dispatchCommit(spec);
      notify();
    }
  }, graceMs);
  entries.set(spec.id, { spec, createdAt, expiresAt, timer });
  notify();
}

/** Cancela un pendiente dentro de su gracia. true si estaba pendiente. */
export function undo(id: string): boolean {
  const e = removeEntry(id);
  if (!e) return false;
  e.spec.onUndo?.();
  notify();
  return true;
}

/** Deshace el pendiente MÁS reciente (createdAt más alto). false si no hay. */
export function undoLatest(): boolean {
  let latest: Entry | null = null;
  for (const e of entries.values()) {
    if (!latest || e.createdAt >= latest.createdAt) latest = e;
  }
  if (!latest) return false;
  return undo(latest.spec.id);
}

/** Commitea TODO lo pendiente ya, por las cadenas por id. Idempotente. */
export function flushAll(_reason: FlushReason): void {
  const snapshot = Array.from(entries.values());
  if (snapshot.length === 0) return;
  for (const e of snapshot) {
    clearTimeout(e.timer);
    entries.delete(e.spec.id);
    dispatchCommit(e.spec);
  }
  notify();
}

/** Pendientes en orden de creación ASCENDENTE (el host reordena para mostrar). */
export function pending(): PendingUndoable[] {
  return Array.from(entries.values())
    .sort((a, b) => a.createdAt - b.createdAt)
    .map((e) => ({
      id: e.spec.id,
      label: e.spec.label,
      createdAt: e.createdAt,
      expiresAt: e.expiresAt,
    }));
}

/** Suscribe un listener a cambios del set de pendientes. Devuelve unsubscribe. */
export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Test-only: limpia estado interno y cadenas por id. */
export function _resetForTests(): void {
  for (const e of entries.values()) clearTimeout(e.timer);
  entries.clear();
  commitChains.clear();
  listeners.clear();
  bypass = false;
}
