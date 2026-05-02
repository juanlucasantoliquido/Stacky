import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/*
 * FA-42 — Suggested next agent.
 * Después de aprobar una exec, sugiere qué agente correr a continuación
 * basado en transiciones históricas (markov). Si no hay datos, usa la
 * cadena clásica del pipeline como fallback.
 */
import { useQuery } from "@tanstack/react-query";
import { Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./NextAgentSuggestion.module.css";
export default function NextAgentSuggestion({ afterAgent }) {
    const { setActiveAgent } = useWorkbench();
    const { data } = useQuery({
        queryKey: ["next-suggestion", afterAgent],
        queryFn: () => Agents.nextSuggestion(afterAgent),
        staleTime: 60_000,
    });
    if (!data || data.length === 0)
        return null;
    return (_jsxs("div", { className: styles.box, children: [_jsx("span", { className: styles.label, children: "siguientes que se suelen correr:" }), data.map((s) => (_jsxs("button", { className: styles.btn, onClick: () => setActiveAgent(s.agent_type), title: s.source === "history"
                    ? `${Math.round(s.probability * 100)}% de los operadores (n=${s.sample_size})`
                    : "Sucesor por defecto del pipeline", children: ["\u2192 ", s.agent_type, _jsx("span", { className: styles.prob, children: s.source === "history"
                            ? ` ${Math.round(s.probability * 100)}%`
                            : " (default)" })] }, s.agent_type)))] }));
}
