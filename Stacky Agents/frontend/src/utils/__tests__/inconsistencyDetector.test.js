/**
 * Tests unitarios — inconsistencyDetector.ts
 *
 * Capa: unit
 * Sin dependencias de DOM.
 *
 * Para ejecutar:
 *   npx vitest run src/utils/__tests__/inconsistencyDetector.test.ts
 */
import { describe, it, expect } from "vitest";
import { detectInconsistency, detectInconsistencyFromRunning, } from "../inconsistencyDetector";
// ─── Fixtures ────────────────────────────────────────────────────────────────
function makeExecution(overrides) {
    return {
        id: 44,
        ticket_id: 1,
        agent_type: "functional",
        status: "running",
        verdict: null,
        input_context: [],
        chain_from: [],
        started_by: "test",
        started_at: "2026-05-14T10:00:00Z",
        ...overrides,
    };
}
// ─── detectInconsistency ──────────────────────────────────────────────────────
describe("detectInconsistency", () => {
    it("no es inconsistente si stacky_status no es 'completed'", () => {
        const exec = makeExecution({ status: "running" });
        const result = detectInconsistency("running", [exec]);
        expect(result.isInconsistent).toBe(false);
        expect(result.orphanExecution).toBeNull();
    });
    it("no es inconsistente si stacky_status es undefined", () => {
        const result = detectInconsistency(undefined, []);
        expect(result.isInconsistent).toBe(false);
    });
    it("detecta INCONSISTENTE cuando completed + ejecución running", () => {
        const exec = makeExecution({ status: "running" });
        const result = detectInconsistency("completed", [exec]);
        expect(result.isInconsistent).toBe(true);
        if (result.isInconsistent) {
            expect(result.orphanExecution.id).toBe(44);
        }
    });
    it("detecta INCONSISTENTE cuando completed + ejecución queued", () => {
        const exec = makeExecution({ status: "queued" });
        const result = detectInconsistency("completed", [exec]);
        expect(result.isInconsistent).toBe(true);
    });
    it("no detecta INCONSISTENTE cuando completed + execuciones terminales", () => {
        const exec1 = makeExecution({ id: 10, status: "completed" });
        const exec2 = makeExecution({ id: 11, status: "error" });
        const result = detectInconsistency("completed", [exec1, exec2]);
        expect(result.isInconsistent).toBe(false);
    });
    it("no detecta INCONSISTENTE cuando completed + lista vacía", () => {
        const result = detectInconsistency("completed", []);
        expect(result.isInconsistent).toBe(false);
    });
    it("retorna la primera ejecución huérfana (running o queued)", () => {
        const exec1 = makeExecution({ id: 44, status: "queued" });
        const exec2 = makeExecution({ id: 45, status: "running" });
        const result = detectInconsistency("completed", [exec1, exec2]);
        expect(result.isInconsistent).toBe(true);
        if (result.isInconsistent) {
            expect(result.orphanExecution.id).toBe(44); // primera del array
        }
    });
});
// ─── detectInconsistencyFromRunning ──────────────────────────────────────────
describe("detectInconsistencyFromRunning", () => {
    it("no es inconsistente si stacky_status no es completed", () => {
        const exec = makeExecution({ status: "running" });
        const result = detectInconsistencyFromRunning("running", exec);
        expect(result.isInconsistent).toBe(false);
    });
    it("no es inconsistente si runningExecution es null", () => {
        const result = detectInconsistencyFromRunning("completed", null);
        expect(result.isInconsistent).toBe(false);
    });
    it("detecta INCONSISTENTE cuando completed + runningExecution presente", () => {
        const exec = makeExecution({ status: "running" });
        const result = detectInconsistencyFromRunning("completed", exec);
        expect(result.isInconsistent).toBe(true);
        if (result.isInconsistent) {
            expect(result.orphanExecution).toBe(exec);
        }
    });
    it("caso ADO-149: execution 44 con stacky_status=completed", () => {
        const exec = makeExecution({ id: 44, status: "running", agent_type: "functional" });
        const result = detectInconsistencyFromRunning("completed", exec);
        expect(result.isInconsistent).toBe(true);
        if (result.isInconsistent) {
            expect(result.orphanExecution.id).toBe(44);
            expect(result.orphanExecution.agent_type).toBe("functional");
        }
    });
});
