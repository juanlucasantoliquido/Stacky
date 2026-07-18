/**
 * Plan 152 F0 — Centro de Actividad: lógica PURA de acumulación de eventos.
 *
 * Sin DOM, sin red, sin timers: solo transformaciones deterministas sobre
 * ActivityState. Todo el comportamiento crítico (dedup, tope, no-leídos,
 * agrupación, mute, hidratación tolerante) vive acá y se blinda con tests
 * puros (no hay @testing-library/react ni jsdom en package.json).
 *
 * NO importa el store singleton (activityCenter.ts); la dirección de la
 * dependencia es reducer ← store, nunca al revés.
 */

export type ActivityKind = "run" | "error" | "cost";
export type Severity = "info" | "success" | "attention" | "error";

export interface ActivityEvent {
  key: string; // dedup, p. ej. "run:1234"
  kind: ActivityKind;
  severity: Severity;
  title: string;
  body?: string;
  ts: number; // epoch ms
  nav?: { tab: string; executionId?: number };
}

export interface ActivityState {
  events: ActivityEvent[];
  lastReadAt: number;
  muted: ActivityKind[];
}

export const ACTIVITY_CAP = 50;
export const LS_STATE_KEY = "stacky.activity.v1"; // única clave localStorage

export function emptyState(): ActivityState {
  return { events: [], lastReadAt: 0, muted: [] };
}

/**
 * Inserta o refresca un evento por su `key`:
 * - DUPLICADO (misma key): conserva el nuevo, no agrega fila.
 * - orden: más nuevo primero (desc por ts).
 * - COLA LLENA: recorta al tope (descarta los más viejos del final).
 */
export function appendEvent(s: ActivityState, e: ActivityEvent): ActivityState {
  const rest = s.events.filter((x) => x.key !== e.key);
  const merged = [e, ...rest].sort((a, b) => b.ts - a.ts);
  return { ...s, events: merged.slice(0, ACTIVITY_CAP) };
}

/** Eventos con ts ESTRICTAMENTE mayor a lastReadAt (borde igual → leído). */
export function unreadCount(s: ActivityState): number {
  return s.events.reduce((n, e) => (e.ts > s.lastReadAt ? n + 1 : n), 0);
}

export function markAllRead(s: ActivityState, nowMs: number): ActivityState {
  return { ...s, lastReadAt: nowMs };
}

/** Agrupa por kind; un kind sin eventos NUNCA crea bucket (§4.5 extensibilidad). */
export function groupByKind(events: ActivityEvent[]): Record<string, ActivityEvent[]> {
  const out: Record<string, ActivityEvent[]> = {};
  for (const e of events) (out[e.kind] ??= []).push(e);
  return out;
}

export function isMuted(s: ActivityState, kind: ActivityKind): boolean {
  return s.muted.includes(kind);
}

export function setMuted(s: ActivityState, kind: ActivityKind, on: boolean): ActivityState {
  const has = s.muted.includes(kind);
  if (on && !has) return { ...s, muted: [...s.muted, kind] };
  if (!on && has) return { ...s, muted: s.muted.filter((k) => k !== kind) };
  return s;
}

/**
 * Deriva la severidad estética de un status de run. Refina combineOutcome (C8):
 * separa `error` (fallo real) de `needs_review` (revisión) — el feed distingue
 * uno de otro, a diferencia de la señal pegajosa del título de pestaña.
 */
export function severityFromRunStatus(status: string): Severity {
  if (status === "error") return "error";
  if (status === "needs_review") return "attention";
  if (status === "completed") return "success";
  return "info"; // cancelled / desconocido: informativo, no alarma
}

/** JSON acotado a ACTIVITY_CAP (la cola ya está recortada por appendEvent). */
export function serializeState(s: ActivityState): string {
  const trimmed: ActivityState = {
    events: s.events.slice(0, ACTIVITY_CAP),
    lastReadAt: s.lastReadAt,
    muted: s.muted,
  };
  return JSON.stringify(trimmed);
}

const KNOWN_KINDS: ActivityKind[] = ["run", "error", "cost"];

function normalizeEvent(x: unknown): ActivityEvent | null {
  if (!x || typeof x !== "object") return null;
  const o = x as Record<string, unknown>;
  if (typeof o.key !== "string") return null;
  if (typeof o.kind !== "string") return null;
  if (typeof o.title !== "string") return null;
  if (typeof o.ts !== "number") return null;
  const severity: Severity =
    o.severity === "success" || o.severity === "attention" || o.severity === "error"
      ? o.severity
      : "info";
  const out: ActivityEvent = {
    key: o.key,
    kind: o.kind as ActivityKind,
    severity,
    title: o.title,
    ts: o.ts,
  };
  if (typeof o.body === "string") out.body = o.body;
  if (o.nav && typeof o.nav === "object") {
    const nav = o.nav as Record<string, unknown>;
    if (typeof nav.tab === "string") {
      out.nav = { tab: nav.tab };
      if (typeof nav.executionId === "number") out.nav.executionId = nav.executionId;
    }
  }
  return out;
}

function normalize(p: unknown): ActivityState {
  if (!p || typeof p !== "object") return emptyState();
  const o = p as Record<string, unknown>;
  const rawEvents = Array.isArray(o.events) ? o.events : [];
  const events = rawEvents
    .map(normalizeEvent)
    .filter((e): e is ActivityEvent => e !== null)
    .sort((a, b) => b.ts - a.ts)
    .slice(0, ACTIVITY_CAP);
  const lastReadAt = typeof o.lastReadAt === "number" ? o.lastReadAt : 0;
  const muted = Array.isArray(o.muted)
    ? (o.muted.filter((k) => KNOWN_KINDS.includes(k as ActivityKind)) as ActivityKind[])
    : [];
  return { events, lastReadAt, muted };
}

/** Tolerante: raw null o JSON inválido → emptyState(). NUNCA lanza. */
export function hydrateState(raw: string | null): ActivityState {
  if (!raw) return emptyState();
  try {
    return normalize(JSON.parse(raw));
  } catch {
    return emptyState();
  }
}
