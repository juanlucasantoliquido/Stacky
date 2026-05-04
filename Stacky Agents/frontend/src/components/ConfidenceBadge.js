import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/*
 * FA-35 — Confidence badge.
 * Renderiza score de confianza del output. < 70 muestra warning visible.
 */
import styles from "./ConfidenceBadge.module.css";
export default function ConfidenceBadge({ overall, signals }) {
    const level = overall >= 80 ? "high" : overall >= 60 ? "mid" : "low";
    const tooltip = signals && signals.length > 0
        ? `Señales detectadas:\n${signals.slice(0, 6).join("\n")}`
        : "Score basado en señales del texto (hedge phrases, longitud, citaciones).";
    return (_jsxs("span", { className: `${styles.badge} ${styles[level]}`, title: tooltip, children: [_jsx("span", { className: styles.icon, children: level === "high" ? "✓" : level === "mid" ? "◐" : "⚠" }), "conf ", overall] }));
}
