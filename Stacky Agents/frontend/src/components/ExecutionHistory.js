import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useQuery } from "@tanstack/react-query";
import { Executions } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./ExecutionHistory.module.css";
export default function ExecutionHistory() {
    const { activeTicketId, activeExecutionId, setActiveExecution } = useWorkbench();
    const { data, isLoading } = useQuery({
        queryKey: ["executions", activeTicketId],
        queryFn: () => Executions.list({ ticket_id: activeTicketId }),
        enabled: activeTicketId != null,
        refetchInterval: 5_000,
    });
    if (!activeTicketId) {
        return (_jsxs("section", { className: styles.section, children: [_jsx("header", { className: styles.head, children: "HISTORIAL" }), _jsx("div", { className: styles.empty, children: _jsx("span", { className: "muted", children: "eleg\u00ED un ticket" }) })] }));
    }
    return (_jsxs("section", { className: styles.section, children: [_jsxs("header", { className: styles.head, children: ["HISTORIAL \u2014 ticket ", activeTicketId] }), _jsxs("div", { className: styles.body, children: [isLoading && _jsx("div", { className: "muted", children: "cargando\u2026" }), !isLoading && (data ?? []).length === 0 && (_jsx("div", { className: "muted", children: "sin ejecuciones" })), (data ?? []).map((e) => (_jsx(Row, { exec: e, active: e.id === activeExecutionId, onClick: () => setActiveExecution(e.id) }, e.id)))] })] }));
}
function Row({ exec, active, onClick, }) {
    const icon = exec.status === "running"
        ? "⏳"
        : exec.verdict === "approved"
            ? "✓"
            : exec.verdict === "discarded" || exec.status === "error"
                ? "✗"
                : "◐";
    return (_jsxs("button", { className: `${styles.row} ${active ? styles.active : ""}`, onClick: onClick, children: [_jsx("span", { className: styles.icon, children: icon }), _jsxs("span", { className: styles.id, children: ["#", exec.id] }), _jsx("span", { className: styles.agent, children: exec.agent_type }), _jsx("span", { className: styles.time, children: new Date(exec.started_at).toLocaleTimeString() })] }));
}
