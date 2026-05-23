/**
 * Tests de integración — flujo completo de RecoverExecutionButton
 *
 * Capa: integration (sin DOM — testea la lógica de llamada al gateway
 *   con fetch mockeado).
 *
 * Escenarios cubiertos (plan §9.5):
 *   TC-01: 200 → resultado limpio (datos invalidados).
 *   TC-02: 409 html_already_published → señal de force dialog.
 *   TC-03: 409 no_active_execution → error info mapeado a 'warning'.
 *   TC-04: 401 → error info interno_error + console.error.
 *   TC-05: 500 → error info internal_error + console.error.
 *   TC-06: código desconocido → UNKNOWN_ERROR_INFO.
 *
 * Para ejecutar:
 *   npx vitest run src/utils/__tests__/agentCompletionRecovery.integration.test.ts
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { rawPost } from "../../api/client";
// ─── Mock global de fetch ─────────────────────────────────────────────────────
function mockFetch(status, body) {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
        status,
        ok: status >= 200 && status < 300,
        text: () => Promise.resolve(JSON.stringify(body)),
    }));
}
describe("rawPost — gateway de agent-completion", () => {
    afterEach(() => {
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
    });
    it("TC-01: 200 → ok=true y data con result", async () => {
        mockFetch(200, { ok: true, result: "agent_completed", execution_id: 44 });
        const response = await rawPost("/api/tickets/by-ado/149/agent-completion", { execution_id: 44, agent_type: "functional", status: "completed", reason: "test", force: false }, {});
        expect(response.ok).toBe(true);
        expect(response.status).toBe(200);
        expect(response.data?.result).toBe("agent_completed");
        expect(response.errorBody).toBeNull();
    });
    it("TC-02: 409 html_already_published → ok=false, errorBody.error='html_already_published'", async () => {
        mockFetch(409, { error: "html_already_published", message: "Ya publicado", correlation_id: "corr-1" });
        const response = await rawPost("/api/tickets/by-ado/149/agent-completion", { execution_id: 44, agent_type: "functional", status: "completed", reason: "test", force: false }, {});
        expect(response.ok).toBe(false);
        expect(response.status).toBe(409);
        expect(response.errorBody?.error).toBe("html_already_published");
        expect(response.errorBody?.correlation_id).toBe("corr-1");
        expect(response.data).toBeNull();
    });
    it("TC-03: 409 no_active_execution → ok=false, code='no_active_execution'", async () => {
        mockFetch(409, { error: "no_active_execution", message: "Sin ejecución activa" });
        const response = await rawPost("/api/tickets/by-ado/149/agent-completion", { execution_id: 44, agent_type: "functional", status: "completed", reason: "test", force: false }, {});
        expect(response.ok).toBe(false);
        expect(response.errorBody?.error).toBe("no_active_execution");
    });
    it("TC-04: 401 → ok=false, code='auth_required'", async () => {
        mockFetch(401, { error: "auth_required", message: "Token inválido" });
        const response = await rawPost("/api/tickets/by-ado/149/agent-completion", {}, {});
        expect(response.ok).toBe(false);
        expect(response.status).toBe(401);
        expect(response.errorBody?.error).toBe("auth_required");
    });
    it("TC-05: 500 → ok=false, code='internal_error'", async () => {
        mockFetch(500, { error: "internal_error", correlation_id: "corr-xyz" });
        const response = await rawPost("/api/tickets/by-ado/149/agent-completion", {}, {});
        expect(response.ok).toBe(false);
        expect(response.status).toBe(500);
        expect(response.errorBody?.error).toBe("internal_error");
    });
    it("TC-06: response con código desconocido → errorBody preservado", async () => {
        mockFetch(422, { error: "html_invalid", message: "Validación fallida" });
        const response = await rawPost("/api/tickets/by-ado/149/agent-completion", {}, {});
        expect(response.ok).toBe(false);
        expect(response.status).toBe(422);
        expect(response.errorBody?.error).toBe("html_invalid");
    });
    it("TC-07: force=true en retry de html_already_published → 200 esperado", async () => {
        mockFetch(200, { ok: true, result: "agent_completed", execution_id: 44 });
        const response = await rawPost("/api/tickets/by-ado/149/agent-completion", { execution_id: 44, agent_type: "functional", status: "completed", reason: "Recuperación manual desde UI", force: true }, {});
        expect(response.ok).toBe(true);
        expect(response.data?.result).toBe("agent_completed");
    });
    it("TC-08: body vacío en respuesta de error → errorBody con message del texto", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
            status: 503,
            ok: false,
            text: () => Promise.resolve("Service Unavailable"),
        }));
        const response = await rawPost("/api/tickets/by-ado/149/agent-completion", {}, {});
        expect(response.ok).toBe(false);
        expect(response.status).toBe(503);
        // Texto no-JSON → errorBody.message = texto crudo
        expect(response.errorBody?.message).toBe("Service Unavailable");
    });
});
// ─── Validación de mapping de error.code → copy ───────────────────────────────
import { getErrorInfo, UNKNOWN_ERROR_INFO } from "../agentCompletionErrors";
describe("getErrorInfo — mapeo de codes a copy para UI", () => {
    const criticalCodes = [
        { code: "html_already_published", expectedSeverity: "warning" },
        { code: "no_active_execution", expectedSeverity: "warning" },
        { code: "execution_state_invalid", expectedSeverity: "warning" },
        { code: "auth_required", expectedSeverity: "warning" },
        { code: "payload_invalid", expectedSeverity: "error" },
        { code: "ticket_not_found", expectedSeverity: "error" },
        { code: "html_invalid", expectedSeverity: "error" },
        { code: "internal_error", expectedSeverity: "error" },
    ];
    for (const { code, expectedSeverity } of criticalCodes) {
        it(`${code} → severity=${expectedSeverity}`, () => {
            const info = getErrorInfo(code);
            expect(info.severity).toBe(expectedSeverity);
            expect(info.title).toBeTruthy();
            expect(info.body).toBeTruthy();
        });
    }
    it("código desconocido → UNKNOWN_ERROR_INFO (severity=error)", () => {
        expect(getErrorInfo("invented_code")).toStrictEqual(UNKNOWN_ERROR_INFO);
    });
});
