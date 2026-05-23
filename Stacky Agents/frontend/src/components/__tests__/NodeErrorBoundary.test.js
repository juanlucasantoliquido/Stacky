import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NodeErrorBoundary } from "../TicketGraphView";
// Silenciar el console.error que React loguea cuando un boundary captura
// un error (no aporta al test, ensucia el output).
beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => { });
});
afterEach(() => {
    cleanup(); // vitest no llama cleanup automático sin configurar globals
    vi.restoreAllMocks();
});
// ── Test fixtures ─────────────────────────────────────────────────────────────
function ThrowingChild({ message = "boom" }) {
    throw new Error(message);
}
function HealthyChild({ children }) {
    return _jsx("div", { "data-testid": "healthy", children: children ?? "ok" });
}
// ── Tests ─────────────────────────────────────────────────────────────────────
describe("NodeErrorBoundary", () => {
    it("renders children when there is no error", () => {
        render(_jsx(NodeErrorBoundary, { adoId: 123, children: _jsx(HealthyChild, { children: "hello" }) }));
        expect(screen.getByTestId("healthy")).toBeTruthy();
        expect(screen.getByTestId("healthy").textContent).toBe("hello");
    });
    it("shows fallback with ADO id when a child throws during render", () => {
        render(_jsx(NodeErrorBoundary, { adoId: 27698, children: _jsx(ThrowingChild, { message: "boundary catches this" }) }));
        // Fallback visible
        const alert = screen.getByRole("alert");
        expect(alert).toBeTruthy();
        expect(alert.textContent).toContain("ADO-27698");
        expect(alert.textContent).toContain("boundary catches this");
        expect(alert.textContent).toContain("Recargá la página");
    });
    it("shows '?' when adoId prop is not provided", () => {
        render(_jsx(NodeErrorBoundary, { children: _jsx(ThrowingChild, { message: "no ado id" }) }));
        const alert = screen.getByRole("alert");
        expect(alert.textContent).toContain("ADO-?");
    });
    it("falls back to generic message when error has no message", () => {
        function ThrowWithoutMessage() {
            throw new Error();
        }
        render(_jsx(NodeErrorBoundary, { adoId: 1, children: _jsx(ThrowWithoutMessage, {}) }));
        const alert = screen.getByRole("alert");
        expect(alert.textContent).toContain("error inesperado");
    });
    it("isolates failures so siblings keep rendering", () => {
        // Múltiples boundaries hermanos. Uno lanza, otro no. El segundo debe
        // mantenerse vivo y visible. Esto valida la promesa del diseño: un nodo
        // roto NO desmonta el árbol completo.
        render(_jsxs("div", { children: [_jsx(NodeErrorBoundary, { adoId: 111, children: _jsx(ThrowingChild, { message: "first crashes" }) }), _jsx(NodeErrorBoundary, { adoId: 222, children: _jsx(HealthyChild, { children: "still alive" }) })] }));
        // El primero muestra fallback con ADO-111
        const alerts = screen.getAllByRole("alert");
        expect(alerts.length).toBe(1);
        expect(alerts[0].textContent).toContain("ADO-111");
        // El segundo sigue renderizando normal
        expect(screen.getByTestId("healthy").textContent).toBe("still alive");
    });
    it("catches errors thrown by deeply nested descendants", () => {
        function Wrapper({ children }) {
            return _jsx("section", { children: _jsx("div", { children: children }) });
        }
        render(_jsx(NodeErrorBoundary, { adoId: 42, children: _jsx(Wrapper, { children: _jsx(Wrapper, { children: _jsx(ThrowingChild, { message: "deep" }) }) }) }));
        const alert = screen.getByRole("alert");
        expect(alert.textContent).toContain("ADO-42");
        expect(alert.textContent).toContain("deep");
    });
});
