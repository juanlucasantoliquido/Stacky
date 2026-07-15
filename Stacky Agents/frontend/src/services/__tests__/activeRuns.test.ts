import { describe, expect, it } from "vitest";
import { mergeActiveRuns } from "../activeRuns";
import type { AgentExecution } from "../../types";

const mk = (id: number, status: string) => ({ id, status } as unknown as AgentExecution);

describe("mergeActiveRuns (plan 134 F0)", () => {
  it("deduplica por id y gana la lista más tardía (running→preparing→queued)", () => {
    const running = [mk(1, "running")];
    const preparing: AgentExecution[] = [];
    const queued = [mk(1, "queued")];
    const result = mergeActiveRuns(running, preparing, queued);
    expect(result).toHaveLength(1);
    expect(result[0].status).toBe("queued");
  });

  it("ordena por id descendente", () => {
    const running = [mk(3, "running")];
    const preparing = [mk(1, "preparing")];
    const queued = [mk(7, "queued")];
    const result = mergeActiveRuns(running, preparing, queued);
    expect(result.map((r) => r.id)).toEqual([7, 3, 1]);
  });

  it("tres listas vacías → []", () => {
    expect(mergeActiveRuns([], [], [])).toEqual([]);
  });
});
