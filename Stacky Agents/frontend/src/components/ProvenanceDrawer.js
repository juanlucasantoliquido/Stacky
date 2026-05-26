import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./ProvenanceDrawer.module.css";
export default function ProvenanceDrawer({ executionId, open, onClose }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    useEffect(() => {
        if (!open || executionId == null)
            return;
        setLoading(true);
        api
            .get(`/api/executions/${executionId}/provenance`)
            .then(setData)
            .catch(() => setData(null))
            .finally(() => setLoading(false));
    }, [open, executionId]);
    if (!open)
        return null;
    return (_jsx("div", { className: styles.backdrop, onClick: (e) => {
            if (e.target === e.currentTarget)
                onClose();
        }, children: _jsxs("aside", { className: styles.drawer, role: "dialog", "aria-label": "Provenance", children: [_jsxs("header", { className: styles.header, children: [_jsx("h3", { children: "\u24D8 C\u00F3mo se construy\u00F3 esto" }), _jsx("button", { className: styles.closeBtn, onClick: onClose, "aria-label": "Cerrar", children: "\u00D7" })] }), _jsxs("div", { className: styles.body, children: [loading && _jsx("p", { className: styles.muted, children: "Cargando\u2026" }), !loading && !data && _jsx("p", { className: styles.muted, children: "No hay datos." }), data && (_jsxs(_Fragment, { children: [_jsxs("dl", { className: styles.list, children: [_jsx("dt", { children: "Modelo" }), _jsx("dd", { children: data.model ?? "(no informado)" }), data.model_reason && (_jsxs(_Fragment, { children: [_jsx("dt", { children: "Por qu\u00E9" }), _jsx("dd", { children: data.model_reason })] })), _jsx("dt", { children: "Tokens" }), _jsxs("dd", { children: [data.tokens_in ?? "?", " entrada / ", data.tokens_out ?? "?", " salida"] }), _jsx("dt", { children: "Costo" }), _jsx("dd", { children: data.cost_usd_total != null
                                                ? `$${data.cost_usd_total.toFixed(4)}`
                                                : "(no calculado)" }), data.confidence != null && (_jsxs(_Fragment, { children: [_jsx("dt", { children: "Confianza" }), _jsxs("dd", { children: [(data.confidence * (data.confidence <= 1 ? 100 : 1)).toFixed(0), "%"] })] })), _jsx("dt", { children: "Duraci\u00F3n" }), _jsx("dd", { children: data.duration_ms != null
                                                ? `${(data.duration_ms / 1000).toFixed(1)}s`
                                                : "—" }), _jsx("dt", { children: "Verdict" }), _jsx("dd", { children: data.verdict ?? "—" })] }), _jsx("h4", { className: styles.subheader, children: "Fuentes usadas" }), data.sources.length === 0 ? (_jsx("p", { className: styles.muted, children: "No se registraron fuentes." })) : (_jsx("ul", { className: styles.sources, children: data.sources.map((s, idx) => (_jsxs("li", { children: [_jsx("span", { className: styles.sourceKind, children: s.kind }), _jsx("span", { children: s.label })] }, idx))) })), data.chain_from.length > 0 && (_jsxs(_Fragment, { children: [_jsx("h4", { className: styles.subheader, children: "Encadenado a" }), _jsx("ul", { className: styles.sources, children: data.chain_from.map((id) => (_jsxs("li", { children: ["Ejecuci\u00F3n #", id] }, id))) })] }))] }))] })] }) }));
}
