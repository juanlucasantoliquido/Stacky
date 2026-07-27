/**
 * pipelineMonitor.ts — Plan 103 F1.
 *
 * Núcleo PURO del monitor del último pipeline: backoff, estados terminales, texto
 * legible y persistencia. Sin React, sin timers, sin red — toda la lógica testeable
 * de forma determinista (en este repo `@testing-library/react` y `jsdom` NO están
 * instalados, así que lo que no viva acá afuera no se puede probar).
 *
 * El store zustand usa `create` plano, mismo precedente que `store/uiSectionsStore.ts:28`.
 */
import { create } from 'zustand';

/** Escalera de sondeo: arranca fino y se relaja. El último valor es el techo. */
export const BACKOFF_STEPS_MS = [3000, 5000, 10000, 30000] as const;

/** Intervalo para el intento N (0-based), con clamp en ambos extremos. */
export function computeBackoffMs(attempt: number): number {
  if (!Number.isFinite(attempt) || attempt < 0) return BACKOFF_STEPS_MS[0];
  const i = Math.min(Math.floor(attempt), BACKOFF_STEPS_MS.length - 1);
  return BACKOFF_STEPS_MS[i];
}

/** Estados en los que el pipeline ya no cambia ⇒ hay que DEJAR de sondear. */
const TERMINALES = new Set([
  'succeeded', 'success', 'completed', 'passed',
  'failed', 'failure', 'error',
  'canceled', 'cancelled', 'skipped',
]);

export function isTerminalStatus(status: string | null | undefined): boolean {
  if (!status) return false;
  return TERMINALES.has(status.trim().toLowerCase());
}

export type MonitorTone = 'running' | 'success' | 'error';

/** Tono del badge. Lo desconocido se trata como "corriendo", nunca como error. */
export function toneForStatus(status: string | null | undefined): MonitorTone {
  const s = (status ?? '').trim().toLowerCase();
  if (['succeeded', 'success', 'completed', 'passed'].includes(s)) return 'success';
  if (['failed', 'failure', 'error', 'canceled', 'cancelled'].includes(s)) return 'error';
  return 'running';
}

const LEGIBLE: Record<string, string> = {
  succeeded: 'terminó bien',
  success: 'terminó bien',
  completed: 'terminó bien',
  passed: 'terminó bien',
  failed: 'falló',
  failure: 'falló',
  error: 'falló',
  canceled: 'cancelado',
  cancelled: 'cancelado',
  skipped: 'salteado',
  running: 'corriendo',
  pending: 'en cola',
  queued: 'en cola',
  created: 'en cola',
  waiting: 'esperando',
};

export interface MonitoredPipeline {
  /** Proyecto activo cuando se disparó. Si cambia el proyecto, el badge no aplica. */
  project: string;
  pipelineId: string;
  ref: string;
  status: string | null;
  webUrl: string | null;
  updatedAt: string;
}

/**
 * Texto del badge en castellano llano. Reemplaza al `JSON.stringify(monitorStatus)`
 * crudo que hoy muestra TriggerPipelineSection.tsx:362.
 */
export function formatMonitorStatus(p: MonitoredPipeline | null): string {
  if (!p) return '';
  const estado = LEGIBLE[(p.status ?? '').trim().toLowerCase()] ?? (p.status || 'sin estado');
  const ref = p.ref ? ` (${p.ref})` : '';
  return `Pipeline ${p.pipelineId}${ref}: ${estado}`;
}

/**
 * 429 del cap de polls (backend/api/ci.py:197, `_MAX_ACTIVE_POLLS_PER_PIPELINE = 5`)
 * NO es un fallo del pipeline: es la señal de "estás sondeando de más". El caller
 * debe subir un escalón de backoff y NO pintar el badge de error.
 */
export function isPollCapError(e: unknown): boolean {
  const m = e instanceof Error ? e.message : String(e);
  return m.startsWith('429') || m.includes('too many active polls');
}

const STORAGE_KEY = 'stacky.devops.lastPipeline';

/** Lee el pipeline persistido. NUNCA lanza: localStorage puede estar denegado o lleno. */
export function loadPersistedPipeline(): MonitoredPipeline | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as Partial<MonitoredPipeline>;
    if (typeof p?.pipelineId !== 'string' || typeof p?.project !== 'string') return null;
    return {
      project: p.project,
      pipelineId: p.pipelineId,
      ref: typeof p.ref === 'string' ? p.ref : '',
      status: typeof p.status === 'string' ? p.status : null,
      webUrl: typeof p.webUrl === 'string' ? p.webUrl : null,
      updatedAt: typeof p.updatedAt === 'string' ? p.updatedAt : '',
    };
  } catch {
    return null; // degradar a memoria es siempre mejor que romper el panel
  }
}

/** Persiste (o borra con `null`). NUNCA lanza. */
export function persist(p: MonitoredPipeline | null): void {
  try {
    if (p === null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    /* sin persistencia el badge sigue andando en memoria */
  }
}

interface MonitorState {
  last: MonitoredPipeline | null;
  attempt: number;
  setLast: (p: MonitoredPipeline) => void;
  updateStatus: (status: string | null, webUrl?: string | null) => void;
  bumpAttempt: () => void;
  resetAttempt: () => void;
  clear: () => void;
}

export const useDevopsMonitorStore = create<MonitorState>((set) => ({
  last: loadPersistedPipeline(),
  attempt: 0,
  setLast: (p) => {
    persist(p);
    set({ last: p, attempt: 0 });
  },
  updateStatus: (status, webUrl) =>
    set((s) => {
      if (!s.last) return s;
      const next: MonitoredPipeline = {
        ...s.last,
        status,
        webUrl: webUrl ?? s.last.webUrl,
        updatedAt: new Date().toISOString(),
      };
      persist(next);
      return { last: next };
    }),
  bumpAttempt: () => set((s) => ({ attempt: s.attempt + 1 })),
  resetAttempt: () => set({ attempt: 0 }),
  clear: () => {
    persist(null);
    set({ last: null, attempt: 0 });
  },
}));

/** El badge solo aplica si el pipeline es del proyecto que el operador está mirando. */
export function appliesToProject(
  p: MonitoredPipeline | null,
  activeProject: string,
): boolean {
  return !!p && !!activeProject && p.project === activeProject;
}
