import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useWorkbench } from "../store/workbench";
import styles from "./TopBar.module.css";
export default function TopBar({ onGoToTeam }) {
    const runningExecutionId = useWorkbench((s) => s.runningExecutionId);
    const isRunning = runningExecutionId != null;
    return (_jsxs("header", { className: styles.bar, children: [_jsxs("div", { className: styles.main, children: [_jsxs("div", { className: styles.brand, children: [onGoToTeam && (_jsx("button", { className: styles.teamBtn, onClick: onGoToTeam, title: "Volver al equipo", children: "\u2190 Equipo" })), _jsx("img", { src: "/stacky-agents-logo.svg", alt: "Stacky", className: styles.logoImg, width: 22, height: 22 }), "Stacky"] }), _jsxs("div", { className: styles.project, children: ["Project ", _jsx("strong", { children: "Strategist_Pacifico" })] }), _jsxs("div", { className: styles.actions, children: [isRunning && (_jsxs("span", { className: styles.runningBadge, children: [_jsx("span", { className: styles.badgeSpinner, "aria-hidden": "true" }), "Agente trabajando\u2026"] })), _jsx("span", { children: "dev@local" })] })] }), isRunning && _jsx("div", { className: styles.progressBar, role: "progressbar", "aria-label": "Ejecuci\u00F3n en progreso" })] }));
}
