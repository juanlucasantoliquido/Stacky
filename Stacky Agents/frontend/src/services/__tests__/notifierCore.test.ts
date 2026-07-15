import { describe, expect, it } from "vitest";
import {
  buildNotificationBody,
  combineOutcome,
  computeTabTitle,
  shouldNotifyExecution,
} from "../notifierCore";

describe("shouldNotifyExecution (plan 134 F2)", () => {
  it("primera vez true, repetido false", () => {
    const seen = new Map<number, number>();
    expect(shouldNotifyExecution(1, 1000, seen)).toBe(true);
    expect(shouldNotifyExecution(1, 1000, seen)).toBe(false);
  });

  it("dos ids distintos en el mismo instante → ambos true", () => {
    const seen = new Map<number, number>();
    expect(shouldNotifyExecution(1, 1000, seen)).toBe(true);
    expect(shouldNotifyExecution(2, 1000, seen)).toBe(true);
  });

  it("pasado el TTL el id vuelve a notificar y el mapa se poda", () => {
    const seen = new Map<number, number>();
    expect(shouldNotifyExecution(1, 0, seen, 1000)).toBe(true);
    expect(shouldNotifyExecution(1, 500, seen, 1000)).toBe(false);
    expect(shouldNotifyExecution(1, 1500, seen, 1000)).toBe(true);
    expect(seen.has(1)).toBe(true);
    expect(seen.get(1)).toBe(1500);
  });
});

describe("combineOutcome (plan 134 F2)", () => {
  it("tabla de verdad", () => {
    expect(combineOutcome(null, "completed")).toBe("ok");
    expect(combineOutcome(null, "error")).toBe("attention");
    expect(combineOutcome(null, "needs_review")).toBe("attention");
    expect(combineOutcome("attention", "completed")).toBe("attention");
    expect(combineOutcome("ok", "cancelled")).toBe("ok");
    expect(combineOutcome(null, "cancelled")).toBe(null);
  });
});

describe("computeTabTitle (plan 134 F2/F3)", () => {
  it("actividad gana, desenlace persiste, base intacta", () => {
    expect(computeTabTitle(3, null, "Stacky Agents")).toBe("(3▶) Stacky Agents");
    expect(computeTabTitle(0, "ok", "Stacky Agents")).toBe("✅ Stacky Agents");
    expect(computeTabTitle(0, "attention", "Stacky Agents")).toBe("❌ Stacky Agents");
    expect(computeTabTitle(0, null, "Stacky Agents")).toBe("Stacky Agents");
    expect(computeTabTitle(2, "attention", "Stacky Agents")).toBe("(2▶) Stacky Agents");
  });
});

describe("buildNotificationBody (plan 134 F2)", () => {
  it("project+título, solo ticket_id, vacío", () => {
    expect(buildNotificationBody({ project: "p", ticket_title: "t" })).toBe("p · t");
    expect(buildNotificationBody({ ticket_id: 7 })).toBe("Ticket 7");
    expect(buildNotificationBody({})).toBe("Ejecución finalizada.");
  });
});
