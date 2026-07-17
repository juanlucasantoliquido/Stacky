import { describe, it, expect } from "vitest";
import { canResolveWithAgent } from "./devResolverModel";

const CLOSED_STATES = ["Done", "Closed", "Resolved", "Removed", "Completed"];

describe("canResolveWithAgent", () => {
  it("Issue + enabled + abierto -> true", () => {
    expect(
      canResolveWithAgent({
        workItemType: "Issue",
        adoState: "New",
        isRunning: false,
        enabled: true,
        closedStates: CLOSED_STATES,
      })
    ).toBe(true);
  });

  it("Task -> false", () => {
    expect(
      canResolveWithAgent({
        workItemType: "Task",
        adoState: "New",
        isRunning: false,
        enabled: true,
        closedStates: CLOSED_STATES,
      })
    ).toBe(false);
  });

  it("cerrado -> false", () => {
    expect(
      canResolveWithAgent({
        workItemType: "Issue",
        adoState: "Done",
        isRunning: false,
        enabled: true,
        closedStates: CLOSED_STATES,
      })
    ).toBe(false);
  });

  it("disabled -> false", () => {
    expect(
      canResolveWithAgent({
        workItemType: "Issue",
        adoState: "New",
        isRunning: false,
        enabled: false,
        closedStates: CLOSED_STATES,
      })
    ).toBe(false);
  });
});
