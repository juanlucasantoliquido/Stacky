import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import styles from "./RunButton.module.css";
export default function RunButton({ state, disabled, onClick, onCancel }) {
    if (state === "running") {
        return (_jsxs("button", { className: `${styles.btn} ${styles.running}`, onClick: onCancel, disabled: !onCancel, title: onCancel ? "Click para cancelar" : "Procesando…", children: [_jsx("span", { className: styles.spinner, "aria-hidden": "true" }), _jsx("span", { children: "Procesando\u2026" }), onCancel && _jsx("span", { className: styles.cancel, children: "\u2715" })] }));
    }
    return (_jsx("button", { className: `${styles.btn} ${styles.idle}`, disabled: disabled, onClick: onClick, children: "\u25B6 RUN AGENT" }));
}
