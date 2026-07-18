/**
 * Plan 151 F0 — Módulo puro de decisión + storage seguro del tour de bienvenida.
 *
 * TODA la lógica de "¿mostrar el tour?", migración de la key vieja y navegación
 * de pasos vive acá, testeable SIN DOM (los tests inyectan un StorageLike).
 * El componente React (OnboardingTour.tsx) queda como cascarón fino.
 */

// ─── Keys (contrato congelado) ────────────────────────────────────────────
export const SEEN_KEY = "stacky_onboarding_seen_v1";
// Migración del prototipo — ÚNICO lugar del literal en todo src/ (KPI-3).
export const LEGACY_SEEN_KEY = "stacky-agents-tour-done";
// Preferencia de auto-show (patrón services/preferences.ts).
export const AUTOSHOW_PREF_KEY = "stacky:onboardingAutoShow";

// C8 — señales de "uso previo" (operador existente), extensible SIN tocar la
// lógica. Cada entrada: key de localStorage cuyo valor JSON-array no vacío
// indica que el operador ya usó la app. Heurística best-effort.
export const PRIOR_USE_SIGNAL_KEYS = ["stacky:pinnedAgents"] as const;

// ─── Storage inyectable (fallback en memoria + tests sin DOM) ──────────────
export interface StorageLike {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
  removeItem(k: string): void;
}

/**
 * Devuelve `localStorage` (envuelto y probado con try/catch) o un store en
 * memoria si `localStorage` no existe o lanza (webview restringido, private
 * browsing). El fallback NO persiste entre recargas — degradación aceptable
 * (§4.6): el tour se muestra igual pero el "visto" no persiste.
 */
export function safeStorage(): StorageLike {
  try {
    const ls = (globalThis as { localStorage?: StorageLike }).localStorage;
    if (!ls) throw new Error("localStorage no disponible");
    const probe = "__stacky_probe__";
    ls.setItem(probe, "1");
    ls.removeItem(probe);
    return ls;
  } catch {
    const mem = new Map<string, string>();
    return {
      getItem: (k) => (mem.has(k) ? mem.get(k)! : null),
      setItem: (k, v) => { mem.set(k, v); },
      removeItem: (k) => { mem.delete(k); },
    };
  }
}

// ─── Señales de uso previo ─────────────────────────────────────────────────
/**
 * true si hay evidencia de que el operador ya usó la app:
 * - legacy key presente, O
 * - alguna key de PRIOR_USE_SIGNAL_KEYS parsea a un array NO vacío.
 * Un valor malformado no cuenta como señal (no crashea).
 */
export function hasPriorUse(s: StorageLike): boolean {
  if (s.getItem(LEGACY_SEEN_KEY) != null) return true;
  for (const key of PRIOR_USE_SIGNAL_KEYS) {
    const raw = s.getItem(key);
    if (raw == null) continue;
    try {
      const v = JSON.parse(raw);
      if (Array.isArray(v) && v.length > 0) return true;
    } catch {
      // malformado => no cuenta como señal
    }
  }
  return false;
}

// ─── Estado del tour ───────────────────────────────────────────────────────
export function isSeen(s: StorageLike): boolean {
  return s.getItem(SEEN_KEY) === "1";
}

/** Preferencia ausente => true (default ON). */
export function isAutoShowEnabled(s: StorageLike): boolean {
  return s.getItem(AUTOSHOW_PREF_KEY) !== "false";
}

/** Decisión de AUTO-show (first-run). Pura. */
export function shouldAutoShow(s: StorageLike): boolean {
  return !isSeen(s) && isAutoShowEnabled(s) && !hasPriorUse(s);
}

export function markSeen(s: StorageLike): void {
  s.setItem(SEEN_KEY, "1");
}

/**
 * C2: resetSeen NO se usa en ningún flujo de producción. Existe SOLO para
 * tests y el smoke manual (limpiar estado). Ningún componente/store la importa.
 */
export function resetSeen(s: StorageLike): void {
  s.removeItem(SEEN_KEY);
}

export function setAutoShow(s: StorageLike, on: boolean): void {
  s.setItem(AUTOSHOW_PREF_KEY, on ? "true" : "false");
}

/**
 * Migración: si la legacy key está presente => tratar como seen v1 (no
 * re-mostrar al operador que ya cerró el prototipo). Idempotente. NO borra la
 * legacy key (solo la lee).
 */
export function migrateLegacy(s: StorageLike): void {
  try {
    if (s.getItem(LEGACY_SEEN_KEY) != null) markSeen(s);
  } catch {
    // no-op
  }
}

// ─── Navegación de pasos (pura) ─────────────────────────────────────────────
export function clampStep(i: number, total: number): number {
  if (i < 0) return 0;
  if (i > total - 1) return total - 1;
  return i;
}

export function nextStep(i: number, total: number): number {
  return Math.min(clampStep(i, total) + 1, total - 1);
}

export function prevStep(i: number): number {
  return Math.max(i - 1, 0);
}

export function isLastStep(i: number, total: number): boolean {
  return i >= total - 1;
}
