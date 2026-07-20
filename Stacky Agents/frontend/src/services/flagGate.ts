/**
 * flagGate.ts — Plan 197 (serie UX). Fuente única de lectura de flags de UI.
 *
 * Semántica fail-open (187 K6): OFF ⇔ value === false literal; key ausente /
 * lista vacía / error de red / value string "false" ⇒ ON. Cache localStorage
 * "stacky.flag.<key>" anti-flash (192 F2).
 *
 * Creado por el primer plan de la serie con lectura de flag frontend que
 * aterriza en el árbol (194 en esta ola; el orden canónico lo asigna al 172).
 * Consumidores (172/173/174/175/185/187/192/194) conservan su wrapper NOMBRADO
 * delegando acá — ver 197 §6.1.
 */
import { HarnessFlags } from "../api/endpoints";

const CACHE_PREFIX = "stacky.flag.";

/**
 * Resolver PURO: dado el array de flags (o null/undefined) y una key, decide
 * si está encendida. Fail-open: SOLO `value === false` literal apaga.
 */
export function flagEnabledFrom(
  flags: ReadonlyArray<{ key: string; value: unknown }> | null | undefined,
  key: string,
): boolean {
  if (!flags) return true; // sin datos aún ⇒ ON (anti-flash)
  const f = flags.find((x) => x.key === key);
  if (!f) return true; // key desconocida por el backend ⇒ ON
  return f.value !== false; // SOLO false explícito apaga
}

// Cache de promesas a nivel módulo: 1 request por sesión y por key.
const _inflight = new Map<string, Promise<boolean>>();

function _writeCache(key: string, on: boolean): void {
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(CACHE_PREFIX + key, on ? "1" : "0");
    }
  } catch {
    /* localStorage no disponible (node/tests o modo privado): no-op */
  }
}

/**
 * Lectura asíncrona con cache de promesa (1 sola llamada a HarnessFlags.list
 * ante N invocaciones). Actualiza el cache localStorage para readCachedBoolFlag.
 */
export function getBoolFlag(key: string): Promise<boolean> {
  const cached = _inflight.get(key);
  if (cached) return cached;
  const p = HarnessFlags.list()
    .then((res) => {
      const on = flagEnabledFrom(res?.flags, key);
      _writeCache(key, on);
      return on;
    })
    .catch(() => {
      // error de red ⇒ fail-open ON; no cachear el fallo (permite reintento)
      _inflight.delete(key);
      return true;
    });
  _inflight.set(key, p);
  return p;
}

/**
 * Lectura SINCRÓNICA desde el cache localStorage; fail-open a true si no hay
 * cache o localStorage no está disponible (vitest node ⇒ stub con vi.stubGlobal).
 */
export function readCachedBoolFlag(key: string): boolean {
  try {
    if (typeof localStorage === "undefined") return true;
    const raw = localStorage.getItem(CACHE_PREFIX + key);
    if (raw === null) return true; // sin cache ⇒ ON
    return raw !== "0";
  } catch {
    return true;
  }
}

/** Test-only: limpia el cache de promesas a nivel módulo (aditivo al contrato §6.1). */
export function resetFlagGateCache(): void {
  _inflight.clear();
}
