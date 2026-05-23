import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/*
 * FA-33 — Cost preview pre-Run.
 * Muestra estimación de tokens, costo USD y latencia para el contexto actual.
 * Si hay cache hit (FA-31), badge "🔁 cached — gratis".
 * Debounced para no saturar al backend mientras el operador edita.
 */
import { useEffect, useState } from "react";
import { Agents } from "../api/endpoints";
import styles from "./CostPreview.module.css";
export default function CostPreview({ agentType, blocks }) {
    const [estimate, setEstimate] = useState(null);
    const [loading, setLoading] = useState(false);
    useEffect(() => {
        if (!agentType || blocks.length === 0) {
            setEstimate(null);
            return;
        }
        let cancelled = false;
        const handle = setTimeout(async () => {
            setLoading(true);
            try {
                const r = await Agents.estimate({ agent_type: agentType, context_blocks: blocks });
                if (!cancelled)
                    setEstimate(r);
            }
            catch {
                if (!cancelled)
                    setEstimate(null);
            }
            finally {
                if (!cancelled)
                    setLoading(false);
            }
        }, 600);
        return () => {
            cancelled = true;
            clearTimeout(handle);
        };
    }, [agentType, blocks]);
    if (!agentType)
        return null;
    if (loading && !estimate) {
        return _jsx("div", { className: styles.box, children: _jsx("span", { className: "muted", children: "estimando\u2026" }) });
    }
    if (!estimate)
        return null;
    if (estimate.cache_hit) {
        return (_jsx("div", { className: `${styles.box} ${styles.cached}`, children: _jsx("span", { title: "Output servido desde cache; sin nueva llamada al LLM", children: "\uD83D\uDD01 cached \u2014 gratis \u00B7 <100ms" }) }));
    }
    const costStr = estimate.cost_usd_total < 0.01
        ? `<$0.01`
        : `$${estimate.cost_usd_total.toFixed(2)}`;
    const latencyStr = estimate.latency_ms < 1000
        ? `${estimate.latency_ms}ms`
        : `${(estimate.latency_ms / 1000).toFixed(1)}s`;
    return (_jsxs("div", { className: styles.box, title: `Modelo: ${estimate.model}`, children: [_jsxs("span", { className: styles.tokens, children: [(estimate.tokens_in / 1000).toFixed(1), "k \u2192 ", (estimate.tokens_out / 1000).toFixed(1), "k tok"] }), _jsx("span", { className: styles.dot, children: "\u00B7" }), _jsx("span", { className: styles.cost, children: costStr }), _jsx("span", { className: styles.dot, children: "\u00B7" }), _jsxs("span", { className: styles.latency, children: ["~", latencyStr] })] }));
}
