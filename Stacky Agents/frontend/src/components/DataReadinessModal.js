import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * DataReadinessModal.tsx — Sprint 9: Data Readiness UI
 *
 * Shows pending data resolution requests for a QA UAT run.
 * Allows operators to:
 *   1. Provide an existing value (e.g. CLCOD)
 *   2. Request SQL seed generation
 *   3. Mark as manual review
 *
 * Props:
 *   runId      — pipeline run identifier (used to locate qa_data_requests.json)
 *   ticketId   — ADO ticket ID (int)
 *   onClose    — close handler
 *   onResolved — called when all pending requests are resolved (triggers pipeline resume)
 *
 * Security:
 *   - Prompt injection check is done server-side (user_data_validator.py).
 *   - No raw PII is rendered; masked values come from the server.
 */
import { useState, useEffect, useCallback } from "react";
import { QaUat } from "../api/endpoints";
import styles from "./DataReadinessModal.module.css";
export default function DataReadinessModal({ runId, ticketId, onClose, onResolved }) {
    const [requests, setRequests] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [activeForm, setActiveForm] = useState(null);
    const [submitting, setSubmitting] = useState(null); // request_id being submitted
    const [validationResults, setValidationResults] = useState({});
    // Per-request resolution artifacts (decisions with questions/options)
    const [artifacts, setArtifacts] = useState({});
    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await QaUat.listDataRequests(runId, ticketId);
            setRequests(res.requests);
            setArtifacts(res.resolution_artifacts ?? {});
        }
        catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
        finally {
            setLoading(false);
        }
    }, [runId, ticketId]);
    useEffect(() => {
        load();
    }, [load]);
    const pendingCount = requests.filter((r) => r.status === "pending_user_input").length;
    function getRequiredFields(req) {
        try {
            return JSON.parse(req.required_fields_json);
        }
        catch {
            return [];
        }
    }
    function initForm(req) {
        const fields = getRequiredFields(req);
        setActiveForm({
            requestId: req.id,
            fields: Object.fromEntries(fields.map((f) => [f, ""])),
        });
        setValidationResults((prev) => {
            const next = { ...prev };
            delete next[req.id];
            return next;
        });
    }
    function cancelForm() {
        setActiveForm(null);
    }
    async function submitValue(req) {
        if (!activeForm || activeForm.requestId !== req.id)
            return;
        const fields = getRequiredFields(req);
        const empty = fields.find((f) => !activeForm.fields[f]?.trim());
        if (empty) {
            setValidationResults((prev) => ({
                ...prev,
                [req.id]: { requestId: req.id, valid: false, message: `El campo ${empty} es obligatorio.` },
            }));
            return;
        }
        setSubmitting(req.id);
        try {
            const res = await QaUat.resolveDataRequest(req.id, {
                resolution_type: "provide_existing_value",
                supplied_fields: activeForm.fields,
                run_id: runId,
                ticket_id: ticketId,
                scenario_id: req.scenario_id,
            });
            if (res.ok && res.result?.validation?.valid !== false) {
                setValidationResults((prev) => ({
                    ...prev,
                    [req.id]: { requestId: req.id, valid: true, message: "Dato válido. Solicitud resuelta." },
                }));
                setActiveForm(null);
                await load();
            }
            else {
                const msg = res.message || (res.result?.validation?.valid === false
                    ? "El valor no cumple los requisitos del escenario."
                    : "Error al resolver la solicitud.");
                setValidationResults((prev) => ({
                    ...prev,
                    [req.id]: { requestId: req.id, valid: false, message: msg },
                }));
            }
        }
        catch (e) {
            setValidationResults((prev) => ({
                ...prev,
                [req.id]: {
                    requestId: req.id,
                    valid: false,
                    message: e instanceof Error ? e.message : "Error inesperado. Revisá los logs.",
                },
            }));
        }
        finally {
            setSubmitting(null);
        }
    }
    async function markManualReview(req) {
        setSubmitting(req.id);
        try {
            await QaUat.resolveDataRequest(req.id, {
                resolution_type: "manual_review",
                run_id: runId,
                ticket_id: ticketId,
                scenario_id: req.scenario_id,
            });
            setActiveForm(null);
            await load();
        }
        catch (e) {
            setValidationResults((prev) => ({
                ...prev,
                [req.id]: {
                    requestId: req.id,
                    valid: false,
                    message: e instanceof Error ? e.message : "Error al marcar revisión manual.",
                },
            }));
        }
        finally {
            setSubmitting(null);
        }
    }
    async function requestSqlSeed(req) {
        setSubmitting(req.id);
        try {
            await QaUat.resolveDataRequest(req.id, {
                resolution_type: "generate_sql_seed",
                run_id: runId,
                ticket_id: ticketId,
                scenario_id: req.scenario_id,
            });
            setActiveForm(null);
            await load();
        }
        catch (e) {
            setValidationResults((prev) => ({
                ...prev,
                [req.id]: {
                    requestId: req.id,
                    valid: false,
                    message: e instanceof Error ? e.message : "Error al solicitar SQL seed.",
                },
            }));
        }
        finally {
            setSubmitting(null);
        }
    }
    // Notify parent when all pending requests are resolved
    useEffect(() => {
        if (!loading && requests.length > 0 && pendingCount === 0 && onResolved) {
            onResolved();
        }
    }, [loading, requests, pendingCount, onResolved]);
    function statusClass(status) {
        if (status === "resolved")
            return styles.statusResolved;
        if (status === "timeout")
            return styles.statusTimeout;
        return styles.statusPending;
    }
    function statusLabel(status) {
        if (status === "resolved")
            return "Resuelto";
        if (status === "timeout")
            return "Expirado";
        return "Pendiente";
    }
    function getQuestion(req) {
        // Try to get question from resolution artifact (broker output)
        const art = artifacts[req.scenario_id];
        if (art?.decisions) {
            const decision = art.decisions.find((d) => d.request_id === req.id);
            if (decision?.question_for_user)
                return decision.question_for_user;
        }
        return req.question || "Se requieren datos para ejecutar este escenario.";
    }
    function getOptions(req) {
        const art = artifacts[req.scenario_id];
        if (art?.decisions) {
            const decision = art.decisions.find((d) => d.request_id === req.id);
            if (decision?.options)
                return decision.options;
        }
        // Fallback options
        const fields = getRequiredFields(req);
        return [
            { id: "provide_existing_value", label: `Ingresar ${fields.join(", ") || "valor"} existente`, requires_input: fields },
            { id: "manual_review", label: "Marcar como revisión manual", requires_input: [] },
        ];
    }
    return (_jsx("div", { className: styles.overlay, onClick: (e) => e.target === e.currentTarget && onClose(), children: _jsxs("div", { className: styles.modal, role: "dialog", "aria-modal": "true", "aria-label": "Data Readiness", children: [_jsxs("div", { className: styles.header, children: [_jsx("span", { className: styles.headerIcon, children: "\uD83D\uDD12" }), _jsx("span", { className: styles.headerTitle, children: "Datos faltantes \u2014 QA UAT" }), pendingCount > 0 ? (_jsxs("span", { className: styles.badgePending, children: [pendingCount, " pendiente", pendingCount > 1 ? "s" : ""] })) : (!loading && _jsx("span", { className: styles.badgeResolved, children: "Todo resuelto" })), _jsx("button", { className: styles.closeBtn, onClick: onClose, title: "Cerrar", children: "\u2715" })] }), _jsxs("div", { className: styles.body, children: [loading && (_jsxs("div", { className: styles.emptyState, children: [_jsx("div", { className: styles.spinner, style: { margin: "0 auto 0.5rem" } }), "Cargando solicitudes de datos..."] })), error && !loading && (_jsxs("div", { className: styles.validationResult + " " + styles.validationError, children: ["Error al cargar solicitudes: ", error] })), !loading && !error && requests.length === 0 && (_jsxs("div", { className: styles.emptyState, children: [_jsx("div", { className: styles.emptyStateIcon, children: "\u2705" }), "No hay solicitudes de datos pendientes para este run."] })), !loading && requests.length > 0 && (_jsxs(_Fragment, { children: [_jsxs("div", { className: styles.contextInfo, children: [_jsxs("strong", { children: ["Run: ", runId, " \u00B7 Ticket #", ticketId] }), "El pipeline detect\u00F3 ", requests.length, " requisito", requests.length > 1 ? "s" : "", " de datos. Resolv\u00E9 cada solicitud para que el agente pueda continuar la ejecuci\u00F3n UAT."] }), requests.map((req) => {
                                    const fields = getRequiredFields(req);
                                    const question = getQuestion(req);
                                    const options = getOptions(req);
                                    const isResolved = req.status !== "pending_user_input";
                                    const isSubmittingThis = submitting === req.id;
                                    const validation = validationResults[req.id];
                                    const isShowingForm = activeForm?.requestId === req.id;
                                    return (_jsxs("div", { className: `${styles.requestCard} ${isResolved ? styles.isResolved : ""}`, children: [_jsxs("div", { className: styles.requestHeader, children: [_jsx("span", { className: styles.requestScenario, children: req.scenario_id }), _jsx("span", { className: `${styles.requestStatus} ${statusClass(req.status)}`, children: statusLabel(req.status) })] }), _jsxs("div", { className: styles.requestBody, children: [_jsx("p", { className: styles.question, children: question }), fields.length > 0 && (_jsxs("div", { className: styles.requiredFields, children: [_jsx("span", { className: styles.requiredFieldsLabel, children: "Campos requeridos:" }), fields.map((f) => (_jsx("span", { className: styles.fieldTag, children: f }, f)))] })), isResolved && (_jsxs("div", { className: styles.resolvedInfo, children: ["\u2713 Resuelto como \u201C", req.resolution_type, "\u201D", req.resolved_by ? ` por ${req.resolved_by}` : "", req.resolved_at ? ` — ${new Date(req.resolved_at).toLocaleString()}` : ""] })), !isResolved && !isShowingForm && (_jsx("div", { className: styles.options, children: options.map((opt) => {
                                                            if (opt.requires_input.length > 0) {
                                                                return (_jsxs("button", { className: `${styles.optionBtn} ${styles.optionBtnPrimary}`, onClick: () => initForm(req), disabled: isSubmittingThis, children: [isSubmittingThis && _jsx("span", { className: styles.spinner }), "\uD83D\uDCDD ", opt.label] }, opt.id));
                                                            }
                                                            if (opt.id === "generate_sql_seed") {
                                                                return (_jsxs("button", { className: styles.optionBtn, onClick: () => requestSqlSeed(req), disabled: isSubmittingThis, children: [isSubmittingThis && _jsx("span", { className: styles.spinner }), "\uD83D\uDDC4 ", opt.label] }, opt.id));
                                                            }
                                                            if (opt.id === "manual_review") {
                                                                return (_jsxs("button", { className: styles.optionBtn, onClick: () => markManualReview(req), disabled: isSubmittingThis, children: [isSubmittingThis && _jsx("span", { className: styles.spinner }), "\uD83D\uDE4B ", opt.label] }, opt.id));
                                                            }
                                                            return (_jsx("button", { className: styles.optionBtn, disabled: isSubmittingThis, children: opt.label }, opt.id));
                                                        }) })), !isResolved && isShowingForm && activeForm && (_jsxs("div", { className: styles.inputForm, children: [Object.keys(activeForm.fields).map((fieldName) => (_jsxs("div", { children: [_jsx("div", { className: styles.inputLabel, children: fieldName }), _jsxs("div", { className: styles.inputRow, children: [_jsx("input", { className: `${styles.inputField} ${validation && !validation.valid ? styles.invalid : ""}`, type: "text", placeholder: `Ingresá ${fieldName}...`, value: activeForm.fields[fieldName], onChange: (e) => setActiveForm((prev) => prev
                                                                                    ? {
                                                                                        ...prev,
                                                                                        fields: { ...prev.fields, [fieldName]: e.target.value },
                                                                                    }
                                                                                    : null), onKeyDown: (e) => e.key === "Enter" && submitValue(req), disabled: isSubmittingThis, autoFocus: true }), _jsx("button", { className: styles.submitBtn, onClick: () => submitValue(req), disabled: isSubmittingThis || !activeForm.fields[fieldName]?.trim(), children: isSubmittingThis ? _jsx("span", { className: styles.spinner }) : "Validar" })] })] }, fieldName))), _jsx("button", { className: styles.cancelBtn, onClick: cancelForm, disabled: isSubmittingThis, children: "Cancelar" })] })), validation && (_jsxs("div", { className: `${styles.validationResult} ${validation.valid ? styles.validationOk : styles.validationError}`, children: [validation.valid ? "✓ " : "✗ ", validation.message] }))] })] }, req.id));
                                })] }))] }), _jsxs("div", { className: styles.footer, children: [_jsx("span", { className: styles.footerInfo, children: pendingCount > 0
                                ? `${pendingCount} solicitud${pendingCount > 1 ? "es" : ""} pendiente${pendingCount > 1 ? "s" : ""} de resolución`
                                : "Todas las solicitudes están resueltas" }), _jsx("button", { className: styles.cancelBtn, onClick: onClose, children: "Cerrar" })] })] }) }));
}
