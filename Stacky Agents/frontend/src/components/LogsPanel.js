import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef } from "react";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { useWorkbench } from "../store/workbench";
import styles from "./LogsPanel.module.css";
export default function LogsPanel() {
    const { runningExecutionId, activeExecutionId } = useWorkbench();
    const target = runningExecutionId ?? activeExecutionId;
    const stream = useExecutionStream(target);
    const ref = useRef(null);
    useEffect(() => {
        if (ref.current)
            ref.current.scrollTop = ref.current.scrollHeight;
    }, [stream.lines.length]);
    return (_jsxs("section", { className: styles.section, children: [_jsxs("header", { className: styles.head, children: ["LOGS ", target ? `— exec #${target}` : "", stream.done ? _jsx("span", { className: "muted", children: " (done)" }) : null] }), _jsxs("div", { className: styles.body, ref: ref, children: [stream.lines.length === 0 && (_jsx("div", { className: "muted", children: "sin logs" })), stream.lines.map((l, i) => (_jsxs("div", { className: `${styles.line} ${styles[l.level]}`, children: [_jsx("span", { className: styles.ts, children: new Date(l.timestamp).toLocaleTimeString() }), _jsx("span", { className: styles.msg, children: l.message })] }, i)))] })] }));
}
