import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/*
 * N3 — TicketFingerprint
 * Muestra el Pre-Analysis Fingerprint (TPAF) de un ticket.
 * Se carga automáticamente al seleccionar un ticket, antes de elegir agente.
 * Informa al operador: tipo de cambio, dominio, complejidad, pack sugerido.
 */
import { useQuery } from "@tanstack/react-query";
import { Tickets } from "../api/endpoints";
import styles from "./TicketFingerprint.module.css";
const COMPLEXITY_LABEL = {
    S: "Simple",
    M: "Mediana",
    L: "Compleja",
    XL: "Muy compleja",
};
const CHANGE_TYPE_LABEL = {
    feature: "Nueva funcionalidad",
    bug: "Bug / Defecto",
    refactor: "Refactor",
    config: "Configuración",
    unknown: "No determinado",
};
const CHANGE_TYPE_ICON = {
    feature: "✦",
    bug: "⚡",
    refactor: "↺",
    config: "⚙",
    unknown: "?",
};
export default function TicketFingerprint({ ticketId, onSuggestPack }) {
    const { data, isLoading, isError } = useQuery({
        queryKey: ["fingerprint", ticketId],
        queryFn: () => Tickets.fingerprint(ticketId),
        staleTime: 5 * 60 * 1000, // 5 min — no re-fetches frecuentes
        retry: false,
    });
    if (isLoading) {
        return (_jsxs("div", { className: styles.loading, children: [_jsx("span", { className: styles.dot }), _jsx("span", { children: "Analizando ticket\u2026" })] }));
    }
    if (isError || !data)
        return null;
    const complexityTier = data.complexity === "S" || data.complexity === "M" ? "low" : "high";
    return (_jsxs("div", { className: styles.panel, children: [_jsxs("div", { className: styles.row, children: [_jsx(Chip, { icon: CHANGE_TYPE_ICON[data.change_type] ?? "?", label: CHANGE_TYPE_LABEL[data.change_type] ?? data.change_type, title: "Tipo de cambio detectado" }), _jsx(Chip, { icon: "\u229E", label: data.domain.join(", "), title: `Dominios detectados (confianza ${Math.round(data.domain_confidence * 100)}%)`, muted: data.domain_confidence < 0.3 }), _jsx(Chip, { icon: "\u2248", label: `${data.complexity} — ${COMPLEXITY_LABEL[data.complexity]}`, title: "Complejidad estimada", tier: complexityTier })] }), data.suggested_pack && (_jsxs("div", { className: styles.packRow, children: [_jsx("span", { className: styles.packLabel, children: "Pack sugerido:" }), _jsxs("button", { className: styles.packBtn, onClick: () => onSuggestPack?.(data.suggested_pack), title: "Iniciar este pack", children: ["\u25B6 ", data.suggested_pack] }), data.keywords_detected.length > 0 && (_jsx("span", { className: styles.keywords, title: "Keywords detectados", children: data.keywords_detected.slice(0, 5).join(" · ") }))] }))] }));
}
function Chip({ icon, label, title, muted, tier, }) {
    return (_jsxs("span", { className: styles.chip, title: title, "data-muted": muted ? "true" : undefined, "data-tier": tier, children: [_jsx("span", { className: styles.chipIcon, children: icon }), _jsx("span", { children: label })] }));
}
