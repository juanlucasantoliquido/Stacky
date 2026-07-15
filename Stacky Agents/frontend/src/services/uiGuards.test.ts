import { describe, expect, it } from "vitest";
import {
  ACTIVE_RUN_STATUSES,
  canGenerateEpic,
  nextConfirmState,
  restoreConsoleDecision,
  shouldCloseOnBackdrop,
  toggleNavTab,
} from "./uiGuards";

describe("shouldCloseOnBackdrop (plan 136 F0)", () => {
  it("pristine+ocioso → true", () => {
    expect(shouldCloseOnBackdrop({ dirty: false, busy: false })).toBe(true);
  });
  it("dirty → false", () => {
    expect(shouldCloseOnBackdrop({ dirty: true, busy: false })).toBe(false);
  });
  it("busy → false", () => {
    expect(shouldCloseOnBackdrop({ dirty: false, busy: true })).toBe(false);
  });
  it("dirty+busy → false", () => {
    expect(shouldCloseOnBackdrop({ dirty: true, busy: true })).toBe(false);
  });
});

describe("canGenerateEpic (plan 136 F0)", () => {
  it("caso feliz → true", () => {
    expect(
      canGenerateEpic({ step: "brief", briefEmpty: false, isLaunching: false, claudeGateBlocked: false }),
    ).toBe(true);
  });
  it("isLaunching:true → false", () => {
    expect(
      canGenerateEpic({ step: "brief", briefEmpty: false, isLaunching: true, claudeGateBlocked: false }),
    ).toBe(false);
  });
  it("briefEmpty:true → false", () => {
    expect(
      canGenerateEpic({ step: "brief", briefEmpty: true, isLaunching: false, claudeGateBlocked: false }),
    ).toBe(false);
  });
  it("step:running → false", () => {
    expect(
      canGenerateEpic({ step: "running", briefEmpty: false, isLaunching: false, claudeGateBlocked: false }),
    ).toBe(false);
  });
  it("claudeGateBlocked:true → false", () => {
    expect(
      canGenerateEpic({ step: "brief", briefEmpty: false, isLaunching: false, claudeGateBlocked: true }),
    ).toBe(false);
  });
});

describe("nextConfirmState (plan 136 F0)", () => {
  it("idle+click → armed,fire:false", () => {
    expect(nextConfirmState("idle", "click")).toEqual({ state: "armed", fire: false });
  });
  it("armed+click → idle,fire:true", () => {
    expect(nextConfirmState("armed", "click")).toEqual({ state: "idle", fire: true });
  });
  it("armed+timeout → idle,fire:false", () => {
    expect(nextConfirmState("armed", "timeout")).toEqual({ state: "idle", fire: false });
  });
  it("idle+timeout → idle,fire:false", () => {
    expect(nextConfirmState("idle", "timeout")).toEqual({ state: "idle", fire: false });
  });
  it("armed+disable → idle,fire:false", () => {
    expect(nextConfirmState("armed", "disable")).toEqual({ state: "idle", fire: false });
  });
});

describe("restoreConsoleDecision (plan 136 F0)", () => {
  it("running/false → keep", () => {
    expect(restoreConsoleDecision("running", false)).toBe("keep");
  });
  it("preparing/false → keep", () => {
    expect(restoreConsoleDecision("preparing", false)).toBe("keep");
  });
  it("queued/false → keep", () => {
    expect(restoreConsoleDecision("queued", false)).toBe("keep");
  });
  it("completed/false → clear", () => {
    expect(restoreConsoleDecision("completed", false)).toBe("clear");
  });
  it("failed/false → clear", () => {
    expect(restoreConsoleDecision("failed", false)).toBe("clear");
  });
  it("undefined/false → clear", () => {
    expect(restoreConsoleDecision(undefined, false)).toBe("clear");
  });
  it("running/true (isError) → clear", () => {
    expect(restoreConsoleDecision("running", true)).toBe("clear");
  });
});

describe("toggleNavTab (plan 136 F0)", () => {
  it("team → tickets", () => {
    expect(toggleNavTab("team")).toBe("tickets");
  });
  it("tickets → team", () => {
    expect(toggleNavTab("tickets")).toBe("team");
  });
  it("docs → team", () => {
    expect(toggleNavTab("docs")).toBe("team");
  });
});

describe("ACTIVE_RUN_STATUSES (plan 136 F0 A2 — sentinela de contrato con plan 134)", () => {
  it("congela el set de estados vivos", () => {
    expect([...ACTIVE_RUN_STATUSES].sort()).toEqual(["preparing", "queued", "running"]);
  });
});
