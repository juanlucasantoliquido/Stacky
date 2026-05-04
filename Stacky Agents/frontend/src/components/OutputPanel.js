import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Executions } from "../api/endpoints";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { useWorkbench } from "../store/workbench";
import ConfidenceBadge from "./ConfidenceBadge";
import ContractBadge from "./ContractBadge";
import DossierPanel from "./DossierPanel";
import NextAgentSuggestion from "./NextAgentSuggestion";
import OutputTools from "./OutputTools";
import StructuredOutput from "./StructuredOutput";
import styles from "./OutputPanel.module.css";
export default function OutputPanel() {
    const { activeExecutionId, runningExecutionId, setRunningExecution } = useWorkbench();
    const qc = useQueryClient();
    const stream = useExecutionStream(runningExecutionId);
    useEffect(() => {
        if (runningExecutionId != null && stream.done) {
            setRunningExecution(null);
        }
    }, [stream.done, runningExecutionId, setRunningExecution]);
    const { data: execution } = useQuery({
        queryKey: ["execution", activeExecutionId],
        queryFn: () => Executions.byId(activeExecutionId),
        enabled: activeExecutionId != null,
        refetchInterval: (q) => {
            const status = q.state.data?.status;
            return status === "running" ? 1500 : false;
        },
    });
    const approve = useMutation({
        mutationFn: (id) => Executions.approve(id),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["execution", activeExecutionId] });
            qc.invalidateQueries({ queryKey: ["executions"] });
        },
    });
    const discard = useMutation({
        mutationFn: (id) => Executions.discard(id),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["execution", activeExecutionId] });
            qc.invalidateQueries({ queryKey: ["executions"] });
        },
    });
    const publish = useMutation({
        mutationFn: (id) => Executions.publish(id),
    });
    if (!activeExecutionId && runningExecutionId == null) {
        return (_jsxs("section", { className: styles.section, children: [_jsx("header", { className: styles.head, children: "OUTPUT" }), _jsx("div", { className: styles.empty, children: _jsxs("p", { className: "muted", children: ["Seleccion\u00E1 un agente y presion\u00E1 ", _jsx("strong", { children: "Run" }), "."] }) })] }));
    }
    if (runningExecutionId != null && !execution) {
        return (_jsxs("section", { className: styles.section, children: [_jsx("header", { className: styles.head, children: "OUTPUT \u2014 running\u2026" }), _jsx("div", { className: styles.empty, children: _jsx("p", { className: "muted", children: "El agente est\u00E1 procesando. Mir\u00E1 los logs abajo." }) })] }));
    }
    if (!execution)
        return null;
    return (_jsxs(_Fragment, { children: [_jsxs("section", { className: styles.section, children: [_jsxs("header", { className: styles.head, children: [_jsxs("span", { style: { display: "flex", alignItems: "center", gap: 8 }, children: [_jsxs("span", { children: ["OUTPUT \u2014 exec #", execution.id, " \u2014 ", execution.agent_type] }), !!execution.metadata?.from_cache && (_jsx("span", { title: "Output servido desde cache", style: { color: "var(--success)" }, children: "\uD83D\uDD01 cached" })), (() => {
                                        const conf = execution.metadata?.confidence;
                                        return conf ? (_jsx(ConfidenceBadge, { overall: conf.overall, signals: conf.signals })) : null;
                                    })()] }), _jsxs("span", { className: styles.status, "data-status": execution.status, children: [execution.status, execution.verdict ? ` (${execution.verdict})` : ""] })] }), _jsxs("div", { className: styles.body, children: [execution.status === "running" && (_jsx("p", { className: "muted", children: "streaming\u2026" })), execution.status === "error" && (_jsx("pre", { className: styles.error, children: execution.error_message })), execution.output && (_jsxs(_Fragment, { children: [execution.contract_result && (_jsx(ContractBadge, { result: execution.contract_result })), _jsx(StructuredOutput, { output: execution.output, agentType: execution.agent_type })] }))] }), execution.status === "completed" && !execution.verdict && (_jsxs("footer", { className: styles.actions, children: [_jsx("button", { className: styles.primary, onClick: () => approve.mutate(execution.id), disabled: approve.isPending, children: "Approve" }), _jsx("button", { className: styles.secondary, onClick: () => publish.mutate(execution.id), disabled: publish.isPending, children: "Send to ADO" }), _jsx("button", { className: styles.secondary, onClick: () => discard.mutate(execution.id), disabled: discard.isPending, children: "Discard" })] })), execution.status === "completed" && execution.output && (_jsx(OutputTools, { executionId: execution.id, agentType: execution.agent_type, output: execution.output })), execution.verdict === "approved" && (_jsx("div", { style: { padding: 12, borderTop: "1px solid var(--border)" }, children: _jsx(NextAgentSuggestion, { afterAgent: execution.agent_type }) }))] }), execution.agent_type === "qa" && (_jsx(DossierPanel, { execution: execution }))] }));
}
