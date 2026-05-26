import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./SavingsCard.module.css";
function formatMs(ms) {
    if (!ms)
        return "0m";
    const totalMin = Math.round(ms / 60000);
    const h = Math.floor(totalMin / 60);
    const m = totalMin % 60;
    if (h === 0)
        return `${m}m`;
    if (m === 0)
        return `${h}h`;
    return `${h}h ${m}m`;
}
export default function SavingsCard() {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    useEffect(() => {
        api
            .get("/api/savings/weekly")
            .then(setData)
            .catch((err) => setError(String(err)));
    }, []);
    if (error)
        return null;
    if (!data) {
        return (_jsx("div", { className: `${styles.card} ${styles.loading}`, "aria-hidden": "true", children: _jsx("span", { children: "Calculando ahorro semanal\u2026" }) }));
    }
    if (data.tickets_closed_with_agents === 0) {
        return (_jsxs("div", { className: styles.card, children: [_jsx("h3", { className: styles.title, children: "\uD83D\uDCCA Esta semana" }), _jsx("p", { className: styles.empty, children: "Todav\u00EDa no cerraste tickets con asistencia de agentes esta semana. Cuando lo hagas, ac\u00E1 vas a ver el ahorro estimado." })] }));
    }
    const savings = data.savings_ms;
    const positive = savings > 0;
    return (_jsxs("div", { className: styles.card, children: [_jsx("h3", { className: styles.title, children: "\uD83D\uDCCA Esta semana" }), _jsx("table", { className: styles.table, children: _jsxs("tbody", { children: [_jsxs("tr", { children: [_jsx("td", { children: "Tickets cerrados con agentes:" }), _jsx("td", { className: styles.value, children: data.tickets_closed_with_agents })] }), _jsxs("tr", { children: [_jsx("td", { children: "Tiempo real:" }), _jsx("td", { className: styles.value, children: formatMs(data.real_time_ms) })] }), _jsxs("tr", { children: [_jsx("td", { children: "Baseline (sin agentes):" }), _jsx("td", { className: styles.value, children: formatMs(data.baseline_time_ms) })] }), _jsxs("tr", { className: positive ? styles.savedRow : styles.lossRow, children: [_jsx("td", { children: _jsx("strong", { children: positive ? "Ahorrado:" : "Tiempo extra:" }) }), _jsx("td", { className: styles.value, children: _jsx("strong", { children: formatMs(Math.abs(savings)) }) })] })] }) }), _jsxs("p", { className: styles.note, children: [data.calibrated ? "✓ " : "⚠ ", data.note] })] }));
}
