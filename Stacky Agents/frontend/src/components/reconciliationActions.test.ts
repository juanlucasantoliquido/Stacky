/**
 * Plan 269 F6 — Tests PUROS de las acciones de reconciliación.
 * Colocado junto al módulo, igual que incidentConsole.test.ts.
 * 7 casos.
 */
import { describe, expect, it } from "vitest";

import {
  CORRECTION_MARKER,
  actionForItem,
  correctionPath,
  type ReconciliationItem,
} from "./reconciliationActions";

function item(kind: string): ReconciliationItem {
  return { execution_id: 41, ticket_id: 77, kind, detail: "detalle" };
}

/** Espejo EXACTO de VALID_TICKET_STATUSES = NON_TERMINAL {idle, running} ∪
 *  TERMINAL {completed, error, cancelled, needs_review}
 *  (backend/services/status_vocabulary.py:11,14,18). Los 6, ni uno más. */
const VALID_TICKET_STATUSES = [
  "completed", "needs_review", "error", "cancelled", "idle", "running",
];

describe("plan 269 F6 — acciones de reconciliación", () => {
  it("1. red_with_delivered_work ofrece marcar terminado", () => {
    const a = actionForItem(item("red_with_delivered_work"));
    expect(a?.targetStatus).toBe("completed");
    expect(a?.confirm).toContain("77");
    expect(a?.label.length).toBeGreaterThan(0);
  });

  it("2. green_with_dirty_close ofrece marcar para revisión", () => {
    const a = actionForItem(item("green_with_dirty_close"));
    expect(a?.targetStatus).toBe("needs_review");
    expect(a?.confirm).toContain("77");
  });

  it("3. los otros 3 kinds no ofrecen acción", () => {
    for (const k of ["unclassified_outcome", "drain_timeout", "green_self_reported_only"]) {
      expect(actionForItem(item(k)), `${k} no deberia ofrecer accion`).toBeNull();
    }
  });

  it("4. un kind del futuro no ofrece acción", () => {
    expect(actionForItem(item("kind_del_futuro"))).toBeNull();
    expect(actionForItem(item(""))).toBeNull();
  });

  it("5. correctionPath nunca usa el camino que publica en el tracker", () => {
    expect(correctionPath(7)).toBe("/api/tickets/7/stacky-status");
    expect(correctionPath(7)).not.toContain("by-ado");
  });

  it("6. targetStatus siempre es un estado válido del vocabulario", () => {
    for (const k of ["red_with_delivered_work", "green_with_dirty_close"]) {
      const a = actionForItem(item(k));
      expect(VALID_TICKET_STATUSES).toContain(a!.targetStatus);
    }
    expect(VALID_TICKET_STATUSES).toHaveLength(6);
  });

  it("7. el reason de falso rojo lleva el marcador de calibración", () => {
    const a = actionForItem(item("red_with_delivered_work"));
    expect(a!.reason.startsWith(CORRECTION_MARKER)).toBe(true);
    // El otro NO lo lleva: no es un acuerdo con el veredicto de falso rojo.
    const b = actionForItem(item("green_with_dirty_close"));
    expect(b!.reason.startsWith(CORRECTION_MARKER)).toBe(false);
  });
});
