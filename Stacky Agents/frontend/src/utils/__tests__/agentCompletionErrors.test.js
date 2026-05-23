/**
 * Tests unitarios — agentCompletionErrors.ts
 *
 * Capa: unit
 * Sin dependencias de DOM. Corren con vitest (configurable en vite.config.ts).
 *
 * Para ejecutar (una vez vitest esté configurado):
 *   npx vitest run src/utils/__tests__/agentCompletionErrors.test.ts
 */
import { describe, it, expect } from "vitest";
import { AGENT_COMPLETION_ERROR_COPY, UNKNOWN_ERROR_INFO, getErrorInfo, } from "../agentCompletionErrors";
describe("AGENT_COMPLETION_ERROR_COPY", () => {
    it("contiene los 8 códigos de error canónicos del plan §7.3", () => {
        const expectedCodes = [
            "payload_invalid",
            "auth_required",
            "ticket_not_found",
            "no_active_execution",
            "execution_state_invalid",
            "html_already_published",
            "html_invalid",
            "internal_error",
        ];
        for (const code of expectedCodes) {
            expect(AGENT_COMPLETION_ERROR_COPY).toHaveProperty(code);
        }
    });
    it("cada entrada tiene title, body, y severity válidos", () => {
        for (const [code, info] of Object.entries(AGENT_COMPLETION_ERROR_COPY)) {
            expect(info.title, `${code} debe tener title`).toBeTruthy();
            expect(info.body, `${code} debe tener body`).toBeTruthy();
            expect(["warning", "error"]).toContain(info.severity);
        }
    });
    it("html_already_published es severity=warning (recuperable con force=true)", () => {
        expect(AGENT_COMPLETION_ERROR_COPY["html_already_published"].severity).toBe("warning");
    });
    it("internal_error es severity=error (bloqueo)", () => {
        expect(AGENT_COMPLETION_ERROR_COPY["internal_error"].severity).toBe("error");
    });
    it("no_active_execution es severity=warning (ya resuelto externamente)", () => {
        expect(AGENT_COMPLETION_ERROR_COPY["no_active_execution"].severity).toBe("warning");
    });
});
describe("getErrorInfo", () => {
    it("devuelve la info correcta para un código conocido", () => {
        const info = getErrorInfo("payload_invalid");
        expect(info.title).toBe("Datos inválidos");
        expect(info.severity).toBe("error");
    });
    it("devuelve UNKNOWN_ERROR_INFO para un código desconocido", () => {
        const info = getErrorInfo("codigo_inventado");
        expect(info).toStrictEqual(UNKNOWN_ERROR_INFO);
        expect(info.severity).toBe("error");
    });
    it("devuelve UNKNOWN_ERROR_INFO si code es undefined", () => {
        const info = getErrorInfo(undefined);
        expect(info).toStrictEqual(UNKNOWN_ERROR_INFO);
    });
    it("devuelve UNKNOWN_ERROR_INFO si code es cadena vacía", () => {
        const info = getErrorInfo("");
        expect(info).toStrictEqual(UNKNOWN_ERROR_INFO);
    });
    it("nunca retorna undefined", () => {
        const codes = [undefined, "", "unknown_invented", "html_already_published", "internal_error"];
        for (const code of codes) {
            expect(getErrorInfo(code)).toBeDefined();
        }
    });
});
