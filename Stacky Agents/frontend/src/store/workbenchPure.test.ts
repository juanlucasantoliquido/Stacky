import { describe, expect, it } from "vitest";
import { migrateWorkbenchPersist, projectChangeReset } from "./workbenchPure";

describe("migrateWorkbenchPersist (plan 136 F0)", () => {
  it("migrate v2 preserva runtime + defaults de consola", () => {
    const r = migrateWorkbenchPersist({ agentRuntime: "codex_cli" }, 2);
    // Plan 265 — el retorno crece con codexConsolePresentation (derivada del legacy: "dock").
    expect(r).toEqual({
      agentRuntime: "codex_cli", codexConsoleExecutionId: null, codexConsoleMinimized: false,
      codexConsolePresentation: "dock",
    });
  });

  it("migrate v1 remapea github_copilot a claude_code_cli", () => {
    const r = migrateWorkbenchPersist({ agentRuntime: "github_copilot" }, 1);
    expect(r.agentRuntime).toBe("claude_code_cli");
  });

  it("migrate v3 completo hace passthrough", () => {
    const r = migrateWorkbenchPersist(
      { agentRuntime: "claude_code_cli", codexConsoleExecutionId: 42, codexConsoleMinimized: true },
      3,
    );
    // Plan 265 — fromVersion 3 (< 4) deriva la presentación del legacy: minimized -> "minimized".
    expect(r).toEqual({
      agentRuntime: "claude_code_cli", codexConsoleExecutionId: 42, codexConsoleMinimized: true,
      codexConsolePresentation: "minimized",
    });
  });

  it("migrate basura (null y {}) → defaults", () => {
    expect(migrateWorkbenchPersist(null, 1)).toEqual({
      agentRuntime: "claude_code_cli", codexConsoleExecutionId: null, codexConsoleMinimized: false,
      codexConsolePresentation: "dock",
    });
    expect(migrateWorkbenchPersist({}, 3)).toEqual({
      agentRuntime: "claude_code_cli", codexConsoleExecutionId: null, codexConsoleMinimized: false,
      codexConsolePresentation: "dock",
    });
  });

  it("migrate v3 con execId no numérico → null", () => {
    const r = migrateWorkbenchPersist({ agentRuntime: "codex_cli", codexConsoleExecutionId: "42" }, 3);
    expect(r.codexConsoleExecutionId).toBeNull();
  });

  // Plan 265 F1 (D5) — WorkbenchPersistV4 agrega codexConsolePresentation.
  it("12. migrar desde fromVersion:3 con codexConsoleMinimized:true -> presentation 'minimized', executionId se conserva", () => {
    const r = migrateWorkbenchPersist(
      { agentRuntime: "codex_cli", codexConsoleExecutionId: 99, codexConsoleMinimized: true },
      3,
    );
    expect(r.codexConsolePresentation).toBe("minimized");
    expect(r.codexConsoleExecutionId).toBe(99);
  });

  it("13. migrar desde fromVersion:4 con codexConsolePresentation:'full' -> 'full'", () => {
    const r = migrateWorkbenchPersist(
      { agentRuntime: "codex_cli", codexConsoleExecutionId: 1, codexConsolePresentation: "full" },
      4,
    );
    expect(r.codexConsolePresentation).toBe("full");
  });

  it("14. migrar desde fromVersion:4 con codexConsolePresentation:'basura' -> 'dock', no lanza", () => {
    const r = migrateWorkbenchPersist(
      { agentRuntime: "codex_cli", codexConsoleExecutionId: 1, codexConsolePresentation: "basura" },
      4,
    );
    expect(r.codexConsolePresentation).toBe("dock");
  });
});

describe("projectChangeReset (plan 136 F0)", () => {
  it("boot (prev null) → null", () => {
    expect(projectChangeReset(null, "A")).toBeNull();
  });

  it("mismo proyecto → null", () => {
    expect(projectChangeReset("A", "A")).toBeNull();
  });

  it("cambio de proyecto → objeto reset con los 5 campos", () => {
    const r = projectChangeReset("A", "B");
    expect(r).toEqual({
      activeTicketId: null,
      activeExecutionId: null,
      blocks: [],
      chatDrawerTicketId: null,
      chatDrawerOpen: false,
    });
  });

  it("proyecto desactivado (nextName null) → objeto reset", () => {
    const r = projectChangeReset("A", null);
    expect(r).toEqual({
      activeTicketId: null,
      activeExecutionId: null,
      blocks: [],
      chatDrawerTicketId: null,
      chatDrawerOpen: false,
    });
  });
});
