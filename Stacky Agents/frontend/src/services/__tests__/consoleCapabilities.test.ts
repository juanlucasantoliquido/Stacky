/**
 * consoleCapabilities.test.ts — Plan 265 F2.5. 8 casos del doc.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/consoleCapabilities.test.ts
 */
import { describe, it, expect } from "vitest";
import { normalizeRuntime, capabilitiesFor } from "../consoleCapabilities";
import type { RuntimeId } from "../consoleCapabilities";

const REAL_RUNTIMES: RuntimeId[] = ["codex_cli", "claude_code_cli", "github_copilot"];
const ALL_RUNTIME_IDS: RuntimeId[] = ["codex_cli", "claude_code_cli", "github_copilot", "unknown"];

describe("consoleCapabilities", () => {
  it("1. normalizeRuntime con los 3 runtimes reales devuelve el mismo id", () => {
    expect(normalizeRuntime("codex_cli")).toBe("codex_cli");
    expect(normalizeRuntime("claude_code_cli")).toBe("claude_code_cli");
    expect(normalizeRuntime("github_copilot")).toBe("github_copilot");
  });

  it("2. normalizeRuntime con null/''/42/'runtime_del_futuro' -> 'unknown', no lanza", () => {
    expect(normalizeRuntime(null)).toBe("unknown");
    expect(normalizeRuntime("")).toBe("unknown");
    expect(normalizeRuntime(42)).toBe("unknown");
    expect(normalizeRuntime("runtime_del_futuro")).toBe("unknown");
  });

  it("3. Paridad: cancel.supported es true en los 3 runtimes reales", () => {
    for (const rt of REAL_RUNTIMES) {
      expect(capabilitiesFor(rt, { hasOrigin: true }).cancel.supported).toBe(true);
    }
  });

  it("4. capabilitiesFor('github_copilot').cancel.note contiene 'cooperativa'", () => {
    const note = capabilitiesFor("github_copilot", { hasOrigin: true }).cancel.note;
    expect(note).not.toBeNull();
    expect(note as string).toContain("cooperativa");
  });

  it("5. capabilitiesFor('unknown'): nada habilitado en silencio en lo que depende del runtime", () => {
    // cancel y modelEffortSlot son las capacidades cuyo valor depende de la
    // IDENTIDAD del runtime (relaunch depende de hasOrigin; repoPanel del
    // workspace) — para "unknown" ninguna de las dos queda supported sin note.
    const caps = capabilitiesFor("unknown", { hasOrigin: true });
    expect(caps.cancel.supported).toBe(true);
    expect(caps.cancel.note).not.toBeNull();
    expect(caps.modelEffortSlot.supported).toBe(false);
    expect(caps.modelEffortSlot.note).not.toBeNull();
  });

  it("6. hasOrigin:false -> relaunch.supported false con note no nula", () => {
    const caps = capabilitiesFor("codex_cli", { hasOrigin: false });
    expect(caps.relaunch.supported).toBe(false);
    expect(caps.relaunch.note).not.toBeNull();
  });

  it("7. modelEffortSlot.supported es false en los 4, con note que nombra el Plan 264", () => {
    for (const rt of ALL_RUNTIME_IDS) {
      const caps = capabilitiesFor(rt, { hasOrigin: true });
      expect(caps.modelEffortSlot.supported).toBe(false);
      expect(caps.modelEffortSlot.note).not.toBeNull();
      expect(caps.modelEffortSlot.note as string).toContain("264");
    }
  });

  it("8. barrido de completitud: cada RuntimeId devuelve las 4 capacidades definidas", () => {
    for (const rt of ALL_RUNTIME_IDS) {
      const caps = capabilitiesFor(rt, { hasOrigin: true });
      expect(caps.cancel).toBeDefined();
      expect(caps.relaunch).toBeDefined();
      expect(caps.modelEffortSlot).toBeDefined();
      expect(caps.repoPanel).toBeDefined();
    }
  });
});
