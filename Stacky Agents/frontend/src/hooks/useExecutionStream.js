import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Executions } from "../api/endpoints";
export function useExecutionStream(executionId) {
    const [state, setState] = useState({ lines: [], done: false });
    const qc = useQueryClient();
    useEffect(() => {
        if (executionId == null) {
            setState({ lines: [], done: false });
            return;
        }
        setState({ lines: [], done: false });
        const es = new EventSource(Executions.streamUrl(executionId));
        const onLog = (e) => {
            const data = JSON.parse(e.data);
            setState((s) => ({ ...s, lines: [...s.lines, data] }));
        };
        const onCompleted = () => {
            setState((s) => ({ ...s, done: true }));
            qc.invalidateQueries({ queryKey: ["execution", executionId] });
            qc.invalidateQueries({ queryKey: ["executions"] });
            es.close();
        };
        const onError = () => {
            setState((s) => ({ ...s, error: "stream error" }));
        };
        es.addEventListener("log", onLog);
        es.addEventListener("completed", onCompleted);
        es.addEventListener("ping", () => { });
        es.onerror = onError;
        return () => {
            es.close();
        };
    }, [executionId, qc]);
    return state;
}
