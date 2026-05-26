import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Executions } from "../api/endpoints";
import { notifyExecutionFinished } from "../services/executionNotifier";
// Reconnect backoff: 1s → 30s. Después de eso emitimos error definitivo.
const RECONNECT_INITIAL_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;
/**
 * Stream SSE de logs de una ejecución.
 *
 * Hardening:
 * - JSON.parse en try/catch: payloads no-JSON o eventos no esperados no
 *   tumban el listener.
 * - Dedup por (timestamp, level, message): si una re-subscripción re-emite
 *   logs ya vistos no se duplican en la UI.
 * - Reconnect automático con backoff exponencial cuando EventSource entra en
 *   estado CLOSED tras un error de red.
 */
export function useExecutionStream(executionId) {
    const [state, setState] = useState({ lines: [], done: false });
    const qc = useQueryClient();
    // Set persistente entre reconexiones del MISMO executionId para dedup.
    const seenKeys = useRef(new Set());
    useEffect(() => {
        if (executionId == null) {
            seenKeys.current = new Set();
            setState({ lines: [], done: false });
            return;
        }
        seenKeys.current = new Set();
        setState({ lines: [], done: false });
        let es = null;
        let retryMs = RECONNECT_INITIAL_MS;
        let retryTimer = null;
        let closed = false;
        const dedupKey = (data) => `${data.timestamp ?? ""}|${data.level ?? ""}|${data.message ?? ""}`;
        const onLog = (e) => {
            let data = null;
            try {
                const parsed = JSON.parse(e.data);
                if (parsed && typeof parsed === "object") {
                    data = parsed;
                }
            }
            catch {
                // payload no-JSON — ignorar silenciosamente
            }
            if (!data)
                return;
            const key = dedupKey(data);
            if (seenKeys.current.has(key))
                return;
            seenKeys.current.add(key);
            setState((s) => ({ ...s, lines: [...s.lines, data] }));
        };
        const onCompleted = (ev) => {
            setState((s) => ({ ...s, done: true }));
            qc.invalidateQueries({ queryKey: ["execution", executionId] });
            qc.invalidateQueries({ queryKey: ["executions"] });
            let agentType = "agente";
            let status = "completed";
            try {
                if (ev?.data) {
                    const parsed = JSON.parse(ev.data);
                    if (parsed?.agent_type)
                        agentType = String(parsed.agent_type);
                    if (parsed?.status)
                        status = parsed.status;
                }
            }
            catch {
                // ignore
            }
            notifyExecutionFinished({ agent_type: agentType, status });
            closed = true;
            es?.close();
        };
        const scheduleReconnect = () => {
            if (closed)
                return;
            if (retryMs > RECONNECT_MAX_MS) {
                setState((s) => ({ ...s, error: "stream error — recargá la página" }));
                return;
            }
            retryTimer = setTimeout(() => {
                retryTimer = null;
                connect();
            }, retryMs);
            retryMs = Math.min(retryMs * 2, RECONNECT_MAX_MS + 1);
        };
        const onError = () => {
            if (closed)
                return;
            // EventSource hace su propio reintento si readyState=CONNECTING, pero si
            // queda CLOSED (cortocircuito de red / servidor 4xx) hay que crear uno nuevo.
            if (es && es.readyState === EventSource.CLOSED) {
                es.close();
                es = null;
                scheduleReconnect();
            }
        };
        const connect = () => {
            es = new EventSource(Executions.streamUrl(executionId));
            es.addEventListener("log", onLog);
            es.addEventListener("completed", onCompleted);
            es.addEventListener("ping", () => { });
            es.addEventListener("open", () => {
                retryMs = RECONNECT_INITIAL_MS;
            });
            es.onerror = onError;
        };
        connect();
        return () => {
            closed = true;
            if (retryTimer)
                clearTimeout(retryTimer);
            es?.close();
        };
    }, [executionId, qc]);
    return state;
}
