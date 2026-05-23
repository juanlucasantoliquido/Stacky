import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { Maximize2, Minimize2, Send, Terminal, X } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Executions } from "../api/endpoints";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { useWorkbench } from "../store/workbench";
import styles from "./CodexConsoleDock.module.css";
export default function CodexConsoleDock() {
    const executionId = useWorkbench((state) => state.codexConsoleExecutionId);
    const minimized = useWorkbench((state) => state.codexConsoleMinimized);
    const setExecution = useWorkbench((state) => state.setCodexConsoleExecution);
    const setMinimized = useWorkbench((state) => state.setCodexConsoleMinimized);
    const [input, setInput] = useState("");
    const stream = useExecutionStream(executionId);
    const executionQ = useQuery({
        queryKey: ["codex-console-execution", executionId],
        queryFn: () => Executions.byId(executionId),
        enabled: executionId != null,
        refetchInterval: stream.done ? false : 5000,
    });
    const sendInput = useMutation({
        mutationFn: (text) => Executions.sendCodexInput(executionId, text),
        onSuccess: () => setInput(""),
    });
    if (executionId == null)
        return null;
    const status = executionQ.data?.status;
    const isCodexRun = executionQ.data?.metadata?.runtime === "codex_cli";
    const canSend = isCodexRun && !sendInput.isPending && input.trim().length > 0;
    const statusLabel = status === "queued"
        ? "preparado"
        : status === "running"
            ? "corriendo"
            : status === "error"
                ? "error"
                : stream.done || status === "completed"
                    ? "finalizada"
                    : "abierta";
    return (_jsxs("section", { className: minimized ? styles.dockMinimized : styles.dock, "aria-label": "Consola Codex", children: [_jsxs("header", { className: styles.header, children: [_jsxs("div", { className: styles.title, children: [_jsx(Terminal, { size: 16 }), _jsx("span", { children: "Codex" }), _jsxs("span", { className: styles.execution, children: ["#", executionId] }), _jsx("span", { className: stream.done ? styles.done : styles.running, children: statusLabel })] }), _jsxs("div", { className: styles.actions, children: [_jsx("button", { type: "button", className: styles.iconButton, onClick: () => setMinimized(!minimized), title: minimized ? "Expandir consola" : "Minimizar consola", children: minimized ? _jsx(Maximize2, { size: 15 }) : _jsx(Minimize2, { size: 15 }) }), _jsx("button", { type: "button", className: styles.iconButton, onClick: () => setExecution(null), title: "Cerrar consola", children: _jsx(X, { size: 15 }) })] })] }), !minimized && (_jsxs("div", { className: styles.body, children: [stream.lines.length === 0 ? (_jsx("div", { className: styles.empty, children: "Esperando salida..." })) : (stream.lines.map((line, index) => (_jsxs("div", { className: `${styles.line} ${styles[line.level] ?? ""}`, children: [_jsx("span", { className: styles.level, children: line.level }), line.group && _jsx("span", { className: styles.group, children: line.group }), _jsx("span", { className: styles.message, children: line.message })] }, `${line.timestamp}-${index}`)))), sendInput.error && (_jsxs("div", { className: `${styles.line} ${styles.error}`, children: [_jsx("span", { className: styles.level, children: "ERROR" }), _jsx("span", { className: styles.group, children: "operator" }), _jsx("span", { className: styles.message, children: sendInput.error.message })] }))] })), !minimized && isCodexRun && (_jsxs("form", { className: styles.inputBar, onSubmit: (event) => {
                    event.preventDefault();
                    const text = input.trim();
                    if (text)
                        sendInput.mutate(text);
                }, children: [_jsx("textarea", { className: styles.input, value: input, onChange: (event) => setInput(event.target.value), placeholder: "Responder a Codex...", rows: 1, onKeyDown: (event) => {
                            if (event.key === "Enter" && !event.shiftKey) {
                                event.preventDefault();
                                const text = input.trim();
                                if (text)
                                    sendInput.mutate(text);
                            }
                        } }), _jsx("button", { type: "submit", className: styles.sendButton, disabled: !canSend, title: "Enviar a Codex", children: _jsx(Send, { size: 15 }) })] }))] }));
}
