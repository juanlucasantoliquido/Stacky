import { describe, expect, it } from "vitest";
import {
  ACTIVE_RUN_STATUSES,
  canGenerateEpic,
  nextConfirmState,
  restoreConsoleDecision,
  sealedWorkItemId,
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

describe("sealedWorkItemId — el guard anti-doble-publicación de la épica", () => {
  it("sello numérico (ADO) → lo devuelve", () => {
    expect(sealedWorkItemId({ epic_ado_id: 1115 })).toBe(1115);
  });
  it("sello STRING (GitLab estringa los ids) → lo devuelve igual, no null", () => {
    // Éste es el caso que producía la épica duplicada: con `typeof === "number"`
    // el guard daba null, el modal creía que nadie había publicado y publicaba
    // una SEGUNDA épica real en GitLab.
    expect(sealedWorkItemId({ epic_ado_id: "1115" })).toBe(1115);
  });
  it("sello de Issue (issue_ado_id) → también cuenta como publicado", () => {
    expect(sealedWorkItemId({ issue_ado_id: 42 })).toBe(42);
  });
  it("sin sello → null", () => {
    expect(sealedWorkItemId({ runtime: "claude_code_cli" })).toBeNull();
  });
  it("metadata ausente → null", () => {
    expect(sealedWorkItemId(undefined)).toBeNull();
    expect(sealedWorkItemId(null)).toBeNull();
  });
  it("basura no numérica → null (no se inventa un id)", () => {
    expect(sealedWorkItemId({ epic_ado_id: "" })).toBeNull();
    expect(sealedWorkItemId({ epic_ado_id: "  " })).toBeNull();
    expect(sealedWorkItemId({ epic_ado_id: "no-es-un-id" })).toBeNull();
    expect(sealedWorkItemId({ epic_ado_id: null })).toBeNull();
    expect(sealedWorkItemId({ epic_ado_id: 0 })).toBeNull();
    expect(sealedWorkItemId({ epic_ado_id: Number.NaN })).toBeNull();
  });
});

// ── Plan 281 F2 (capa 1) — el header que hacía desaparecer el body ───────────
//
// `cabecerasDeSync` vive en el hook `useTicketSync` pero se prueba acá porque en
// este repo NO hay RTL ni jsdom: la lógica testeable de UI va en `.ts` puro.
describe("cabecerasDeSync (plan 281 F2)", () => {
  it("declara Content-Type application/json", async () => {
    const { cabecerasDeSync } = await import("../hooks/useTicketSync");
    // Sin esto el navegador manda text/plain y Flask descarta el body ENTERO:
    // el backend nunca recibe {"project": "..."} y rutea por el proyecto activo
    // global en vez del que el operador mira.
    expect(cabecerasDeSync("auto_poll")["Content-Type"]).toBe("application/json");
  });
  it("conserva el trigger", async () => {
    const { cabecerasDeSync } = await import("../hooks/useTicketSync");
    expect(cabecerasDeSync("startup")["X-Stacky-Trigger"]).toBe("startup");
  });
});
