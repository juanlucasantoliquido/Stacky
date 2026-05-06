import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import styles from "./PipelineStatus.module.css";
const STAGE_ORDER = ["business", "functional", "technical", "developer", "qa"];
const STAGE_ICONS = {
    business: "💼",
    functional: "🔍",
    technical: "🔬",
    developer: "🚀",
    qa: "✅",
};
const STAGE_SHORT = {
    business: "Negocio",
    functional: "Funcional",
    technical: "Técnico",
    developer: "Dev",
    qa: "QA",
};
export default function PipelineStatus({ result, compact = false }) {
    const pct = Math.round(result.overall_progress * 100);
    return (_jsxs("div", { className: `${styles.root} ${compact ? styles.compact : ""}`, children: [_jsx("div", { className: styles.progressBar, children: _jsx("div", { className: styles.progressFill, style: { width: `${pct}%` } }) }), _jsx("div", { className: styles.stages, children: STAGE_ORDER.map((stage) => {
                    const s = result.stages[stage];
                    if (!s)
                        return null;
                    const isNext = stage === result.next_suggested;
                    return (_jsxs("div", { className: [
                            styles.stage,
                            s.done ? styles.done : styles.pending,
                            isNext ? styles.next : "",
                        ].join(" "), title: s.evidence || s.label, children: [_jsx("span", { className: styles.stageIcon, children: STAGE_ICONS[stage] }), !compact && (_jsx("span", { className: styles.stageLabel, children: STAGE_SHORT[stage] })), s.done && (_jsx("span", { className: styles.checkmark, children: "\u2713" })), !s.done && isNext && (_jsx("span", { className: styles.arrow, children: "\u2192" }))] }, stage));
                }) }), !compact && result.summary && (_jsx("p", { className: styles.summary, children: result.summary })), !compact && (_jsxs("div", { className: styles.meta, children: [_jsxs("span", { children: [pct, "% completado"] }), result.next_suggested && (_jsxs("span", { className: styles.nextLabel, children: ["Pr\u00F3ximo: ", _jsx("strong", { children: STAGE_SHORT[result.next_suggested] ?? result.next_suggested })] })), _jsxs("span", { className: styles.source, children: [result.source === "cache" ? "⚡ cache" : "🤖 LLM", " · ", result.model_used] })] }))] }));
}
