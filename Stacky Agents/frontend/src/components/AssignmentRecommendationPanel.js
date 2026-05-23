import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * AssignmentRecommendationPanel — Panel de recomendacion de asignacion P6.
 *
 * Human-in-the-loop obligatorio:
 * 1. El operador solicita recomendaciones.
 * 2. Ve la lista de candidatos con scores y razones explicables.
 * 3. Selecciona un candidato.
 * 4. Ve un preview (dry_run) de lo que se cambiara en ADO.
 * 5. Confirma explicitamente (boton "Confirmar asignacion").
 * 6. Solo entonces se llama a POST /api/tickets/{id}/assign con dry_run=false.
 *
 * advisory_only: el panel nunca aplica nada sin confirmacion del operador.
 */
import { useState, useCallback } from "react";
import styles from "./AssignmentRecommendationPanel.module.css";
const API_BASE = window.__STACKY_API_BASE__ ?? "";
async function fetchJson(url, opts) {
    const resp = await fetch(`${API_BASE}${url}`, {
        headers: { "Content-Type": "application/json" },
        ...opts,
    });
    return resp.json();
}
export function AssignmentRecommendationPanel({ ticket, onAssigned, }) {
    const [open, setOpen] = useState(false);
    const [phase, setPhase] = useState("idle");
    const [candidates, setCandidates] = useState([]);
    const [selected, setSelected] = useState(null);
    const [dryRunResult, setDryRunResult] = useState(null);
    const [error, setError] = useState(null);
    const handleOpen = useCallback(async () => {
        setOpen(true);
        setPhase("loading");
        setError(null);
        setCandidates([]);
        setSelected(null);
        setDryRunResult(null);
        try {
            const data = await fetchJson(`/api/tickets/${ticket.id}/assignment-recommendations`, {
                method: "POST",
                body: JSON.stringify({}),
            });
            if (!data.ok) {
                setError(data.message || data.error || "Error al cargar recomendaciones");
                setPhase("error");
                return;
            }
            if (data.error === "no_users_configured") {
                setError("No hay usuarios configurados. Ejecuta 'Sincronizar usuarios desde ADO' primero.");
                setPhase("error");
                return;
            }
            setCandidates(data.candidates || []);
            setPhase("recommendations");
        }
        catch (e) {
            setError(e.message || "Error de red");
            setPhase("error");
        }
    }, [ticket.id]);
    const handleSelectCandidate = useCallback(async (candidate) => {
        setSelected(candidate);
        setPhase("confirming");
        setError(null);
        // Dry-run preview
        try {
            const data = await fetchJson(`/api/tickets/${ticket.id}/assign`, {
                method: "POST",
                body: JSON.stringify({ ado_unique_name: candidate.ado_unique_name, dry_run: true }),
            });
            if (data.ok) {
                setDryRunResult(data);
            }
            else {
                setError(data.message || "Error en preview");
            }
        }
        catch (e) {
            setError(e.message || "Error de red en preview");
        }
    }, [ticket.id]);
    const handleConfirm = useCallback(async () => {
        if (!selected)
            return;
        setPhase("applying");
        setError(null);
        try {
            const data = await fetchJson(`/api/tickets/${ticket.id}/assign`, {
                method: "POST",
                body: JSON.stringify({
                    ado_unique_name: selected.ado_unique_name,
                    dry_run: false,
                    reason: `Asignado por recomendacion Stacky — score ${selected.score.toFixed(2)}`,
                }),
            });
            if (data.ok && data.ado_updated) {
                setPhase("done");
                onAssigned();
            }
            else {
                setError(data.message || "Error al aplicar asignacion en ADO");
                setPhase("confirming");
            }
        }
        catch (e) {
            setError(e.message || "Error de red al aplicar");
            setPhase("confirming");
        }
    }, [selected, ticket.id, onAssigned]);
    const handleClose = useCallback(() => {
        setOpen(false);
        setPhase("idle");
        setSelected(null);
        setError(null);
        setDryRunResult(null);
    }, []);
    // Solo mostrar el boton si el ticket no tiene asignado
    const showButton = !ticket.assigned_to_ado;
    return (_jsxs("div", { className: styles.panel, children: [_jsxs("div", { className: styles.header, children: [_jsx("span", { children: "Asignacion" }), ticket.assigned_to_ado ? (_jsxs("span", { style: { color: "#6b7280", fontWeight: "normal" }, children: ["Asignado: ", ticket.assigned_to_ado] })) : (!open && (_jsx("button", { className: styles.openBtn, onClick: handleOpen, children: "Sugerir asignacion" })))] }), open && (_jsxs("div", { className: styles.body, children: [phase === "loading" && (_jsx("div", { className: styles.loading, children: "Calculando recomendaciones..." })), phase === "error" && (_jsxs(_Fragment, { children: [error?.includes("no hay usuarios") || error?.includes("no_users_configured") ? (_jsxs("div", { className: styles.noUsers, children: [error, _jsx("br", {}), _jsx("small", { children: "Usa el boton de sincronizacion de usuarios o configura manualmente en la BD." })] })) : (_jsx("div", { className: styles.error, children: error })), _jsxs("div", { style: { marginTop: 8, display: "flex", gap: 8 }, children: [_jsx("button", { className: styles.btnSecondary, onClick: handleOpen, children: "Reintentar" }), _jsx("button", { className: styles.btnSecondary, onClick: handleClose, children: "Cerrar" })] })] })), phase === "recommendations" && (_jsxs(_Fragment, { children: [candidates.length === 0 ? (_jsx("div", { className: styles.loading, children: "No hay candidatos disponibles con los filtros actuales." })) : (_jsx("div", { className: styles.candidateList, children: candidates.map((c) => (_jsxs("div", { className: [
                                        styles.candidateCard,
                                        c.overloaded ? styles.overloaded : "",
                                    ].join(" "), onClick: () => !c.overloaded && handleSelectCandidate(c), children: [_jsxs("div", { className: styles.candidateInfo, children: [_jsx("div", { className: styles.candidateName, children: c.display_name }), _jsxs("div", { className: styles.candidateMeta, children: [c.active_tickets, " tickets activos \u00B7 Carga: ", c.load_pct.toFixed(0), "%", c.type_affinity.match && (_jsxs(_Fragment, { children: [" \u00B7 Especialista en ", ticket.work_item_type] }))] }), _jsx("div", { className: styles.candidateReason, children: c.reason }), c.recommendation_flags.includes("overloaded") && (_jsx("span", { className: styles.badge, children: "Sobrecargado" })), c.recommendation_flags.includes("no_type_specialization") && (_jsx("span", { className: styles.badgeWarn, children: "Sin especializacion en tipo" }))] }), _jsxs("div", { className: styles.scoreBar, children: [_jsxs("div", { className: styles.rank, children: ["#", c.rank] }), _jsxs("div", { className: styles.scoreValue, children: [(c.score * 100).toFixed(0), "%"] })] })] }, c.ado_unique_name))) })), _jsx("div", { className: styles.advisory, children: "Recomendacion solo consultiva (advisory_only). La asignacion requiere confirmacion explicita del operador antes de escribir en ADO." }), _jsx("button", { className: styles.btnSecondary, style: { marginTop: 10 }, onClick: handleClose, children: "Cancelar" })] })), phase === "confirming" && selected && (_jsxs("div", { className: styles.confirmBox, children: [_jsx("div", { className: styles.confirmTitle, children: "Confirmar asignacion en ADO" }), _jsxs("div", { className: styles.confirmDetail, children: [_jsx("strong", { children: "Ticket:" }), " ADO-", ticket.ado_id, " \u2014 ", ticket.title, _jsx("br", {}), _jsx("strong", { children: "Asignar a:" }), " ", selected.display_name, " (", selected.ado_unique_name, ")", _jsx("br", {}), _jsx("strong", { children: "Score:" }), " ", (selected.score * 100).toFixed(0), "%", _jsx("br", {}), _jsx("strong", { children: "Razon:" }), " ", selected.reason] }), dryRunResult && (_jsxs("div", { style: { fontSize: 11, color: "#374151", marginBottom: 10 }, children: [_jsx("strong", { children: "Se ejecutara en ADO:" }), dryRunResult.actions.map((a) => (_jsx("div", { style: { fontFamily: "monospace", marginTop: 2 }, children: a.would_call }, a.action)))] })), error && _jsx("div", { className: styles.error, children: error }), _jsxs("div", { className: styles.confirmActions, children: [_jsx("button", { className: styles.btnPrimary, onClick: handleConfirm, children: "Confirmar asignacion" }), _jsx("button", { className: styles.btnSecondary, onClick: () => { setPhase("recommendations"); setSelected(null); }, children: "Volver a candidatos" }), _jsx("button", { className: styles.btnDanger, onClick: handleClose, children: "Cancelar" })] })] })), phase === "applying" && (_jsx("div", { className: styles.loading, children: "Aplicando asignacion en ADO..." })), phase === "done" && (_jsxs("div", { className: styles.success, children: ["Asignacion aplicada correctamente en ADO. El ticket fue sincronizado.", _jsx("button", { className: styles.btnSecondary, style: { marginLeft: 10 }, onClick: handleClose, children: "Cerrar" })] }))] }))] }));
}
export default AssignmentRecommendationPanel;
