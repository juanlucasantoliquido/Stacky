import { jsx as _jsx } from "react/jsx-runtime";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useExecutionStream } from "../useExecutionStream";
// ── Mock de EventSource ──────────────────────────────────────────────────────
class FakeEventSource {
    static instances = [];
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSED = 2;
    url;
    readyState = FakeEventSource.OPEN;
    onerror = null;
    listeners = {};
    constructor(url) {
        this.url = url;
        FakeEventSource.instances.push(this);
    }
    addEventListener(type, fn) {
        (this.listeners[type] ||= []).push(fn);
    }
    removeEventListener(type, fn) {
        if (!this.listeners[type])
            return;
        this.listeners[type] = this.listeners[type].filter((h) => h !== fn);
    }
    close() {
        this.readyState = FakeEventSource.CLOSED;
    }
    // Helpers para el test
    emit(type, data) {
        const ev = new MessageEvent(type, { data: typeof data === "string" ? data : JSON.stringify(data) });
        (this.listeners[type] || []).forEach((h) => h(ev));
    }
    emitRaw(type, raw) {
        const ev = new MessageEvent(type, { data: raw });
        (this.listeners[type] || []).forEach((h) => h(ev));
    }
}
vi.mock("../../api/endpoints", () => ({
    Executions: {
        streamUrl: (id) => `/api/executions/${id}/logs/stream`,
    },
}));
beforeEach(() => {
    FakeEventSource.instances = [];
    // @ts-expect-error — installing a global stub for the test
    globalThis.EventSource = FakeEventSource;
});
afterEach(() => {
    vi.restoreAllMocks();
});
function wrapper({ children }) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return _jsx(QueryClientProvider, { client: qc, children: children });
}
// ── Tests ────────────────────────────────────────────────────────────────────
describe("useExecutionStream", () => {
    it("dedupes log lines by (timestamp,level,message)", () => {
        const { result } = renderHook(() => useExecutionStream(42), { wrapper });
        const es = FakeEventSource.instances[0];
        const log = { timestamp: "2026-05-15T10:00:00Z", level: "info", message: "hola" };
        act(() => {
            es.emit("log", log);
            es.emit("log", log); // duplicate — debe ser descartado
            es.emit("log", { ...log, message: "otro" });
        });
        expect(result.current.lines).toHaveLength(2);
        expect(result.current.lines.map((l) => l.message)).toEqual(["hola", "otro"]);
    });
    it("tolerates non-JSON payloads without breaking subsequent logs", () => {
        const { result } = renderHook(() => useExecutionStream(43), { wrapper });
        const es = FakeEventSource.instances[0];
        act(() => {
            es.emitRaw("log", "{not json"); // payload corrupto
            es.emitRaw("log", "null"); // JSON pero no-object
            es.emit("log", { timestamp: "t1", level: "warn", message: "después" });
        });
        expect(result.current.lines).toHaveLength(1);
        expect(result.current.lines[0]?.message).toBe("después");
        expect(result.current.error).toBeUndefined();
    });
    it("marks done=true on completed event and closes the stream", () => {
        const { result } = renderHook(() => useExecutionStream(44), { wrapper });
        const es = FakeEventSource.instances[0];
        act(() => {
            es.emit("completed", { type: "completed" });
        });
        expect(result.current.done).toBe(true);
        expect(es.readyState).toBe(FakeEventSource.CLOSED);
    });
    it("does not add ping events to lines", () => {
        const { result } = renderHook(() => useExecutionStream(45), { wrapper });
        const es = FakeEventSource.instances[0];
        act(() => {
            es.emit("ping", { type: "ping" });
            es.emit("ping", { type: "ping" });
        });
        expect(result.current.lines).toHaveLength(0);
    });
    it("resets state when executionId changes to null", () => {
        const { result, rerender } = renderHook(({ id }) => useExecutionStream(id), { wrapper, initialProps: { id: 50 } });
        const es = FakeEventSource.instances[0];
        act(() => {
            es.emit("log", { timestamp: "t", level: "info", message: "x" });
        });
        expect(result.current.lines).toHaveLength(1);
        rerender({ id: null });
        expect(result.current.lines).toEqual([]);
        expect(result.current.done).toBe(false);
    });
});
