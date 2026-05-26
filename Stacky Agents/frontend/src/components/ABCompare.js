import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./ABCompare.module.css";
const COLUMN_LABELS = ["Variante A", "Variante B", "Variante C", "Variante D"];
export default function ABCompare({ executionIds, onPickWinner, onClose }) {
    const [executions, setExecutions] = useState([]);
    const [winnerId, setWinnerId] = useState(null);
    useEffect(() => {
        let cancelled = false;
        Promise.all(executionIds.map((id) => api
            .get(`/api/executions/${id}`)
            .catch(() => null))).then((results) => {
            if (!cancelled)
                setExecutions(results);
        });
        return () => {
            cancelled = true;
        };
    }, [executionIds]);
    const handlePick = (id) => {
        setWinnerId(id);
        onPickWinner?.(id);
    };
    return (_jsxs("div", { className: styles.overlay, role: "dialog", "aria-modal": "true", children: [_jsxs("header", { className: styles.header, children: [_jsx("h2", { children: "Comparar variantes" }), _jsx("button", { className: styles.closeBtn, onClick: onClose, "aria-label": "Cerrar", children: "\u00D7" })] }), _jsx("div", { className: styles.grid, style: { gridTemplateColumns: `repeat(${executions.length}, 1fr)` }, children: executions.map((ex, idx) => (_jsxs("div", { className: `${styles.column} ${winnerId === ex?.id ? styles.winner : ""}`, children: [_jsxs("div", { className: styles.colHeader, children: [_jsx("strong", { children: COLUMN_LABELS[idx] ?? `Variante ${idx + 1}` }), ex && (_jsx("span", { className: styles.modelTag, children: ex.metadata?.model ?? ex.metadata?.routing_decision?.model ?? "—" }))] }), ex == null ? (_jsx("p", { className: styles.muted, children: "No se pudo cargar." })) : (_jsxs(_Fragment, { children: [_jsx("pre", { className: styles.output, children: ex.output ?? "(sin output)" }), _jsx("button", { className: `${styles.pickBtn} ${winnerId === ex.id ? styles.picked : ""}`, onClick: () => handlePick(ex.id), disabled: winnerId === ex.id, children: winnerId === ex.id ? "✓ Elegida" : "Elegir" })] }))] }, idx))) })] }));
}
