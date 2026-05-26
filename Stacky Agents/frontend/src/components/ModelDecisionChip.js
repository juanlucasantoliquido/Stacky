import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import styles from "./ModelDecisionChip.module.css";
const ALT_MODELS = ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"];
const MODEL_LABEL = {
    "claude-opus-4-7": "Opus",
    "claude-sonnet-4-6": "Sonnet",
    "claude-haiku-4-5": "Haiku",
};
export default function ModelDecisionChip({ decision, onRerun }) {
    const [expanded, setExpanded] = useState(false);
    if (!decision || !decision.model)
        return null;
    const cost = decision.cost_estimate;
    const costStr = typeof cost === "number" && Number.isFinite(cost)
        ? ` ($${cost.toFixed(2)})`
        : "";
    const modelLabel = MODEL_LABEL[decision.model] ?? decision.model;
    const alternatives = ALT_MODELS.filter((m) => m !== decision.model);
    return (_jsxs("div", { className: styles.wrap, children: [_jsxs("button", { className: styles.chip, onClick: () => setExpanded((v) => !v), "aria-expanded": expanded, title: decision.reason ?? "Decisión de routing", children: [_jsx("span", { "aria-hidden": "true", children: "\u24D8" }), "Modelo: ", modelLabel, costStr] }), expanded && (_jsxs("div", { className: styles.detail, children: [_jsxs("p", { className: styles.reason, children: [_jsx("strong", { children: "Por qu\u00E9:" }), " ", decision.reason ?? "(no informado)"] }), onRerun && (_jsxs("div", { className: styles.rerunRow, children: [_jsx("span", { className: styles.rerunLabel, children: "Re-correr con:" }), alternatives.map((m) => (_jsx("button", { className: styles.rerunBtn, onClick: () => onRerun(m), children: MODEL_LABEL[m] ?? m }, m)))] }))] }))] }));
}
