import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/*
 * N1 — ContractBadge
 * Muestra el resultado del Contract Validator para una ejecución completada.
 * Score 0–100 con colores, lista de failures (errors) y warnings colapsable.
 */
import { useState } from "react";
import styles from "./ContractBadge.module.css";
export default function ContractBadge({ result }) {
    const [expanded, setExpanded] = useState(false);
    const totalIssues = result.failures.length + result.warnings.length;
    const tier = result.score >= 90
        ? "pass"
        : result.score >= 70
            ? "warn"
            : "fail";
    const tierLabel = tier === "pass" ? "OK" : tier === "warn" ? "REVISAR" : "FALLO";
    return (_jsxs("div", { className: styles.badge, "data-tier": tier, children: [_jsxs("button", { className: styles.header, onClick: () => totalIssues > 0 && setExpanded((v) => !v), "aria-expanded": expanded, title: totalIssues > 0 ? "Ver detalles del contrato" : undefined, children: [_jsx("span", { className: styles.label, children: "CONTRATO" }), _jsxs("span", { className: styles.score, children: [result.score, "/100"] }), _jsx("span", { className: styles.status, children: tierLabel }), totalIssues > 0 && (_jsxs("span", { className: styles.count, children: [result.failures.length > 0 && (_jsxs("span", { "data-sev": "error", children: [result.failures.length, " \u2717"] })), result.warnings.length > 0 && (_jsxs("span", { "data-sev": "warning", children: [result.warnings.length, " \u26A0"] })), _jsx("span", { className: styles.chevron, children: expanded ? "▲" : "▼" })] }))] }), expanded && totalIssues > 0 && (_jsxs("ul", { className: styles.list, children: [result.failures.map((f, i) => (_jsxs("li", { "data-sev": "error", className: styles.item, children: [_jsx("span", { className: styles.sev, children: "\u2717" }), _jsx("span", { children: f.message })] }, `e-${i}`))), result.warnings.map((w, i) => (_jsxs("li", { "data-sev": "warning", className: styles.item, children: [_jsx("span", { className: styles.sev, children: "\u26A0" }), _jsx("span", { children: w.message })] }, `w-${i}`)))] }))] }));
}
