import { describe, expect, it } from "vitest";
import { migrateWorkbenchPersist, projectChangeReset } from "./workbenchPure";

describe("migrateWorkbenchPersist (plan 136 F0)", () => {
  it("migrate v2 preserva runtime + defaults de consola", () => {
    const r = migrateWorkbenchPersist({ agentRuntime: "codex_cli" }, 2);
    expect(r).toEqual({ agentRuntime: "codex_cli", codexConsoleExecutionId: null, codexConsoleMinimized: false });
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
    expect(r).toEqual({ agentRuntime: "claude_code_cli", codexConsoleExecutionId: 42, codexConsoleMinimized: true });
  });

  it("migrate basura (null y {}) → defaults", () => {
    expect(migrateWorkbenchPersist(null, 1)).toEqual({
      agentRuntime: "claude_code_cli", codexConsoleExecutionId: null, codexConsoleMinimized: false,
    });
    expect(migrateWorkbenchPersist({}, 3)).toEqual({
      agentRuntime: "claude_code_cli", codexConsoleExecutionId: null, codexConsoleMinimized: false,
    });
  });

  it("migrate v3 con execId no numérico → null", () => {
    const r = migrateWorkbenchPersist({ agentRuntime: "codex_cli", codexConsoleExecutionId: "42" }, 3);
    expect(r.codexConsoleExecutionId).toBeNull();
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
