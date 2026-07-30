/**
 * consoleActions.test.ts — Plan 265 F3. 12 casos del doc.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/consoleActions.test.ts
 *
 * Test 11 (D1/E2): gatea que la consola nunca use Agents.cancel / /api/agents/cancel.
 * La cadena prohibida se construye en runtime, NUNCA literal (si se escribe
 * literal, este mismo archivo matchearía su propio gate).
 */
import { describe, it, expect } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  availableActions,
  requiresConfirmation,
  confirmationText,
  CANCELLABLE_STATUSES,
} from "../consoleActions";
import type { ExecutionSnapshot } from "../consoleActions";

function snap(overrides: Partial<ExecutionSnapshot>): ExecutionSnapshot {
  return { status: "running", runtime: "codex_cli", hasOrigin: true, ...overrides };
}

describe("consoleActions", () => {
  it("1. status running, runtime codex_cli: cancel presente y enabled", () => {
    const acts = availableActions(snap({ status: "running", runtime: "codex_cli" }));
    const cancel = acts.find((a) => a.id === "cancel");
    expect(cancel).toBeDefined();
    expect(cancel?.enabled).toBe(true);
  });

  it("2. status completed: cancel presente pero enabled:false, reason no nulo", () => {
    const acts = availableActions(snap({ status: "completed" }));
    const cancel = acts.find((a) => a.id === "cancel");
    expect(cancel).toBeDefined();
    expect(cancel?.enabled).toBe(false);
    expect(cancel?.reason).not.toBeNull();
  });

  it("3. status running, runtime github_copilot: cancel enabled (paridad) y reason con 'cooperativa'", () => {
    const acts = availableActions(snap({ status: "running", runtime: "github_copilot" }));
    const cancel = acts.find((a) => a.id === "cancel");
    expect(cancel?.enabled).toBe(true);
    expect(cancel?.reason).toContain("cooperativa");
  });

  it("4. hasOrigin false: relaunch enabled:false con motivo", () => {
    const acts = availableActions(snap({ hasOrigin: false }));
    const relaunch = acts.find((a) => a.id === "relaunch");
    expect(relaunch?.enabled).toBe(false);
    expect(relaunch?.reason).not.toBeNull();
  });

  it("5. status null (deploy viejo / snapshot incompleto): no lanza, nada habilitado por accidente", () => {
    expect(() => availableActions(snap({ status: null }))).not.toThrow();
    const acts = availableActions(snap({ status: null }));
    const cancel = acts.find((a) => a.id === "cancel");
    expect(cancel?.enabled).toBe(false);
  });

  it("6. requiresConfirmation('cancel') true", () => {
    expect(requiresConfirmation("cancel")).toBe(true);
  });

  it("7. requiresConfirmation('relaunch' | 'copyAll' | 'close') false", () => {
    expect(requiresConfirmation("relaunch")).toBe(false);
    expect(requiresConfirmation("copyAll")).toBe(false);
    expect(requiresConfirmation("close")).toBe(false);
  });

  it("8. confirmationText('cancel', 42) contiene '42' y 'cancelar'", () => {
    const text = confirmationText("cancel", 42);
    expect(text).toContain("42");
    expect(text.toLowerCase()).toContain("cancelar");
  });

  it("9. CANCELLABLE_STATUSES es exactamente el espejo del backend", () => {
    expect(CANCELLABLE_STATUSES).toEqual(new Set(["vscode_chat", "preparing", "queued", "running"]));
  });

  it("10. sesión zombie (running pero el stream ya emitió done): cancel sigue enabled", () => {
    const acts = availableActions(snap({ status: "running" }));
    const cancel = acts.find((a) => a.id === "cancel");
    expect(cancel?.enabled).toBe(true);
  });

  it("11. gate de endpoint (D1): los archivos de consola nunca mencionan el camino sin gate de 409", () => {
    const forbidden = ["Agents" + ".cancel", "/api/agents" + "/cancel"];
    const dir = path.resolve(__dirname, "..");
    const consoleFiles = fs
      .readdirSync(dir)
      .filter((f) => f.startsWith("console") && (f.endsWith(".ts") || f.endsWith(".tsx")));
    expect(consoleFiles.length).toBeGreaterThan(0);
    for (const file of consoleFiles) {
      const text = fs.readFileSync(path.join(dir, file), "utf8");
      for (const bad of forbidden) {
        expect(text.includes(bad)).toBe(false);
      }
    }
  });

  it("12. sesión muerta sin estado: status 'cancelled' y stream cerrado -> cancel disabled, relaunch depende de hasOrigin, nada lanza", () => {
    expect(() => availableActions(snap({ status: "cancelled" }))).not.toThrow();
    const acts = availableActions(snap({ status: "cancelled", hasOrigin: true }));
    const cancel = acts.find((a) => a.id === "cancel");
    const relaunch = acts.find((a) => a.id === "relaunch");
    expect(cancel?.enabled).toBe(false);
    expect(relaunch?.enabled).toBe(true);
  });
});
