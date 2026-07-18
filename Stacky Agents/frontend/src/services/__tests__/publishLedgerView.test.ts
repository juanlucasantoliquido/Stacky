import { describe, it, expect } from "vitest";
import { partitionLedger, ledgerRowLabel, canRepublish } from "../publishLedgerView";
import type { PublishLedgerItem, PublishLedgerSnapshot } from "../../api/endpoints";

function item(overrides: Partial<PublishLedgerItem>): PublishLedgerItem {
  return {
    id: 1,
    execution_id: 1,
    status: "pending",
    created_at: "2026-07-01T00:00:00",
    updated_at: "2026-07-01T00:00:00",
    ado_ids: null,
    error: null,
    source: "runtime",
    ...overrides,
  };
}

describe("partitionLedger", () => {
  it("concatena pending_stale + failed y ordena por updated_at desc", () => {
    const snap: PublishLedgerSnapshot = {
      enabled: true,
      pending_stale: [item({ execution_id: 338, updated_at: "2026-07-01T10:00:00" })],
      failed: [item({ execution_id: 339, status: "failed", updated_at: "2026-07-01T12:00:00" })],
      counts: {},
    };
    const { actionable, empty } = partitionLedger(snap);
    expect(empty).toBe(false);
    expect(actionable.map((i) => i.execution_id)).toEqual([339, 338]); // 12:00 antes que 10:00
  });

  it("empty true cuando no hay filas accionables", () => {
    const snap: PublishLedgerSnapshot = {
      enabled: true, pending_stale: [], failed: [], counts: {},
    };
    expect(partitionLedger(snap).empty).toBe(true);
  });
});

describe("ledgerRowLabel", () => {
  it("usa el literal 'sin error registrado' cuando no hay error", () => {
    const label = ledgerRowLabel(item({ execution_id: 338, status: "pending", error: null }));
    expect(label).toContain("exec 338");
    expect(label).toContain("pending");
    expect(label).toContain("sin error registrado");
  });

  it("incluye el error cuando existe", () => {
    const label = ledgerRowLabel(item({ execution_id: 340, status: "failed", error: "boom" }));
    expect(label).toContain("boom");
    expect(label).not.toContain("sin error registrado");
  });
});

describe("canRepublish", () => {
  it("false solo para posted", () => {
    expect(canRepublish(item({ status: "posted" }))).toBe(false);
    expect(canRepublish(item({ status: "pending" }))).toBe(true);
    expect(canRepublish(item({ status: "failed" }))).toBe(true);
  });
});
