import { describe, it, expect, afterEach } from "vitest";
import {
  SEEN_KEY,
  LEGACY_SEEN_KEY,
  AUTOSHOW_PREF_KEY,
  PRIOR_USE_SIGNAL_KEYS,
  safeStorage,
  hasPriorUse,
  isSeen,
  isAutoShowEnabled,
  shouldAutoShow,
  markSeen,
  resetSeen,
  setAutoShow,
  migrateLegacy,
  clampStep,
  nextStep,
  prevStep,
  isLastStep,
  type StorageLike,
} from "../onboarding";
import { STEPS, DECLARED_ANCHORS } from "../onboardingSteps";

/** StorageLike de mentira (Map-backed): no toca localStorage real ni el DOM. */
function memStore(seed?: Record<string, string>): StorageLike {
  const mem = new Map<string, string>(Object.entries(seed ?? {}));
  return {
    getItem: (k) => (mem.has(k) ? mem.get(k)! : null),
    setItem: (k, v) => { mem.set(k, v); },
    removeItem: (k) => { mem.delete(k); },
  };
}

describe("Plan 151 F0 — shouldAutoShow", () => {
  it("1. storage vacío ⇒ true (first-run real)", () => {
    expect(shouldAutoShow(memStore())).toBe(true);
  });

  it("2. SEEN_KEY='1' ⇒ false", () => {
    expect(shouldAutoShow(memStore({ [SEEN_KEY]: "1" }))).toBe(false);
  });

  it("3. pref AUTOSHOW_PREF_KEY='false' ⇒ false", () => {
    expect(shouldAutoShow(memStore({ [AUTOSHOW_PREF_KEY]: "false" }))).toBe(false);
  });

  it("4. legacy key presente ⇒ false (hasPriorUse)", () => {
    expect(shouldAutoShow(memStore({ [LEGACY_SEEN_KEY]: "1" }))).toBe(false);
  });

  it("5. pinnedAgents no vacío ⇒ false (operador existente)", () => {
    const s = memStore({ "stacky:pinnedAgents": '["a.agent.md"]' });
    expect(shouldAutoShow(s)).toBe(false);
  });

  it("6. pinnedAgents='[]' y resto vacío ⇒ true", () => {
    const s = memStore({ "stacky:pinnedAgents": "[]" });
    expect(shouldAutoShow(s)).toBe(true);
  });
});

describe("Plan 151 F0 — migrateLegacy", () => {
  it("7. legacy presente ⇒ isSeen==true, shouldAutoShow==false; idempotente", () => {
    const s = memStore({ [LEGACY_SEEN_KEY]: "1" });
    migrateLegacy(s);
    expect(isSeen(s)).toBe(true);
    expect(shouldAutoShow(s)).toBe(false);
    // idempotente: 2ª llamada no cambia nada
    migrateLegacy(s);
    expect(isSeen(s)).toBe(true);
  });

  it("7b. sin legacy ⇒ no marca seen", () => {
    const s = memStore();
    migrateLegacy(s);
    expect(isSeen(s)).toBe(false);
  });
});

describe("Plan 151 F0 — safeStorage fallback", () => {
  afterEach(() => {
    // limpiar cualquier mock de localStorage global inyectado
    delete (globalThis as Record<string, unknown>).localStorage;
  });

  it("8. localStorage que lanza en setItem ⇒ store en memoria funcional", () => {
    const throwing = {
      getItem: () => null,
      setItem: () => { throw new Error("QuotaExceeded / disabled"); },
      removeItem: () => { throw new Error("disabled"); },
    };
    (globalThis as Record<string, unknown>).localStorage = throwing;
    const s = safeStorage();
    // el store devuelto NO es el throwing: markSeen/isSeen funcionan en memoria
    markSeen(s);
    expect(isSeen(s)).toBe(true);
    resetSeen(s);
    expect(isSeen(s)).toBe(false);
  });

  it("8b. sin localStorage (node) ⇒ fallback en memoria funcional", () => {
    // en el entorno node de vitest no hay localStorage global
    const s = safeStorage();
    setAutoShow(s, false);
    expect(isAutoShowEnabled(s)).toBe(false);
  });
});

describe("Plan 151 F0 — navegación de pasos (total=6)", () => {
  const total = 6;
  it("9a. clampStep en bordes", () => {
    expect(clampStep(-1, total)).toBe(0);
    expect(clampStep(0, total)).toBe(0);
    expect(clampStep(5, total)).toBe(5);
    expect(clampStep(99, total)).toBe(5);
  });
  it("9b. nextStep clampea al último", () => {
    expect(nextStep(0, total)).toBe(1);
    expect(nextStep(5, total)).toBe(5);
    expect(nextStep(99, total)).toBe(5);
  });
  it("9c. prevStep clampea a 0", () => {
    expect(prevStep(1)).toBe(0);
    expect(prevStep(0)).toBe(0);
    expect(prevStep(-3)).toBe(0);
  });
  it("9d. isLastStep", () => {
    expect(isLastStep(5, total)).toBe(true);
    expect(isLastStep(4, total)).toBe(false);
  });
});

describe("Plan 151 F0 — prefs y reset", () => {
  it("10. setAutoShow(false) ⇒ isAutoShowEnabled false; resetSeen ⇒ isSeen false", () => {
    const s = memStore({ [SEEN_KEY]: "1" });
    setAutoShow(s, false);
    expect(isAutoShowEnabled(s)).toBe(false);
    resetSeen(s);
    expect(isSeen(s)).toBe(false);
    setAutoShow(s, true);
    expect(isAutoShowEnabled(s)).toBe(true);
  });

  it("10b. pref ausente ⇒ default ON (true)", () => {
    expect(isAutoShowEnabled(memStore())).toBe(true);
  });
});

describe("Plan 151 F0 — hasPriorUse itera PRIOR_USE_SIGNAL_KEYS (C8)", () => {
  it("11a. cada key de la lista con array no vacío ⇒ true (parametrizado sobre la lista real)", () => {
    for (const key of PRIOR_USE_SIGNAL_KEYS) {
      const s = memStore({ [key]: '["x"]' });
      expect(hasPriorUse(s)).toBe(true);
    }
  });
  it("11b. valor malformado no cuenta como señal ⇒ false (no crashea)", () => {
    const key = PRIOR_USE_SIGNAL_KEYS[0];
    const s = memStore({ [key]: "{not-json" });
    expect(hasPriorUse(s)).toBe(false);
  });
  it("11c. array vacío no cuenta como señal ⇒ false", () => {
    const key = PRIOR_USE_SIGNAL_KEYS[0];
    const s = memStore({ [key]: "[]" });
    expect(hasPriorUse(s)).toBe(false);
  });
  it("11d. la lista es no vacía (contrato extensible)", () => {
    expect(PRIOR_USE_SIGNAL_KEYS.length).toBeGreaterThan(0);
  });
});

describe("Plan 151 F0 — invariante C2 (on-demand no borra seen)", () => {
  it("12. tras markSeen, nada en producción llama resetSeen ⇒ isSeen sigue true y shouldAutoShow false", () => {
    const s = memStore();
    markSeen(s);
    // simular abrir on-demand: el store llama requestOpenTour (NO resetSeen).
    // Aquí solo verificamos la invariante de datos: seen persiste.
    expect(isSeen(s)).toBe(true);
    expect(shouldAutoShow(s)).toBe(false);
  });

  it("12b. keys congeladas (contrato KPI-3)", () => {
    expect(SEEN_KEY).toBe("stacky_onboarding_seen_v1");
    expect(AUTOSHOW_PREF_KEY).toBe("stacky:onboardingAutoShow");
    // La legacy key es la fuente de migración; su literal vive ÚNICAMENTE en
    // onboarding.ts (KPI-3), por eso acá solo verificamos su forma, no el texto.
    expect(LEGACY_SEEN_KEY.startsWith("stacky-agents-tour")).toBe(true);
  });
});

describe("Plan 151 F1 — stepAnchors", () => {
  it("stepAnchorsAreDeclared: 0 anclas huérfanas", () => {
    const declared = new Set<string>(DECLARED_ANCHORS);
    for (const step of STEPS) {
      if (step.target == null) continue;
      const m = step.target.match(/\[data-tour="([^"]+)"\]/);
      expect(m, `target mal formado: ${step.target}`).not.toBeNull();
      const anchor = m![1];
      expect(declared.has(anchor), `ancla huérfana: ${anchor}`).toBe(true);
    }
  });

  it("stepsAreNonEmpty: title/body no vacíos y 4..6 pasos", () => {
    expect(STEPS.length).toBeGreaterThanOrEqual(4);
    expect(STEPS.length).toBeLessThanOrEqual(6);
    for (const step of STEPS) {
      expect(step.title.trim().length).toBeGreaterThan(0);
      expect(step.body.trim().length).toBeGreaterThan(0);
      expect(step.id.trim().length).toBeGreaterThan(0);
    }
  });
});
