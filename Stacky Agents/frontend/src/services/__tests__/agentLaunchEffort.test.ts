// Plan 212 F2 — el effort elegido llega al backend por el canal correcto, y NO
// se cuela por el de Copilot (ese runtime no tiene efforts).
import { describe, it, expect, vi, beforeEach } from "vitest";

const runWithOptions = vi.fn(async () => ({ execution_id: 1, status: "queued" }));
const openChat = vi.fn(async () => ({ ok: true }));

vi.mock("../../api/endpoints", () => ({
  Agents: {
    runWithOptions: (p: unknown) => runWithOptions(p as never),
    openChat: (p: unknown) => openChat(p as never),
  },
}));

import { launchAgentWithRuntime } from "../agentLaunch";

const agenteVsCode = {
  filename: "Developer.agent.md",
  system_prompt: "sos un dev",
} as never;

const base = {
  ticketId: 7,
  projectName: "RSPacifico",
  contextBlocks: [],
  vscodeAgent: agenteVsCode,
};

describe("launchAgentWithRuntime — effort", () => {
  beforeEach(() => {
    runWithOptions.mockClear();
    openChat.mockClear();
  });

  it("propaga effort a runWithOptions", async () => {
    await launchAgentWithRuntime({ ...base, runtime: "claude_code_cli", effort: "high" });

    expect(runWithOptions).toHaveBeenCalledTimes(1);
    expect(runWithOptions.mock.calls[0][0]).toMatchObject({ effort: "high" });
  });

  it("no rompe cuando effort es undefined", async () => {
    await launchAgentWithRuntime({ ...base, runtime: "claude_code_cli" });

    const payload = runWithOptions.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.effort).toBeUndefined();
  });

  it("no manda effort por openChat (copilot)", async () => {
    await launchAgentWithRuntime({ ...base, runtime: "github_copilot", effort: "max" });

    expect(runWithOptions).not.toHaveBeenCalled();
    const payload = openChat.mock.calls[0][0] as Record<string, unknown>;
    expect("effort" in payload).toBe(false);
  });
});
