import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * FinishWorkButton — Cierre manual fallback (Fase 4 del plan ADO delegation).
 *
 * Visible cuando un ticket NO está en stacky_status='completed' y tampoco está
 * en un ado_state cerrado. Permite al operador:
 *   1. Hacer dry-run para ver precondiciones (HTML existe, status actual).
 *   2. Confirmar el cierre, que dispara: publish HTML → update ADO state →
 *      marcar stacky_status='completed' → registrar audit en system_logs.
 *
 * Diseño UX:
 *   - Primer click abre modal con campos y muestra dry-run automático al abrir.
 *   - El usuario revisa precondiciones, escribe motivo, confirma.
 *   - Cada acción del backend se muestra con su ok/reason individual.
 */
import { useState, useCallback, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Tickets } from "../api/endpoints";
import styles from "./FinishWorkButton.module.css";
export default function FinishWorkButton({ ticket, disabled, onCompleted }) {
    const [open, setOpen] = useState(false);
    const [reason, setReason] = useState("");
    const [publishToAdo, setPublishToAdo] = useState(true);
    const [targetState, setTargetState] = useState("");
    const [forcePublish, setForcePublish] = useState(false);
    const [lastResult, setLastResult] = useState(null);
    const [confirming, setConfirming] = useState(false);
    const dryRunMutation = useMutation({
        mutationFn: () => Tickets.finishWork(ticket.id, {
            operator_reason: reason.trim() || "(dry-run preview)",
            publish_to_ado: publishToAdo,
            target_ado_state: targetState.trim() || null,
            dry_run: true,
        }),
        onSuccess: (data) => setLastResult(data),
    });
    const finalMutation = useMutation({
        mutationFn: () => Tickets.finishWork(ticket.id, {
            operator_reason: reason.trim(),
            publish_to_ado: publishToAdo,
            target_ado_state: targetState.trim() || null,
            force_publish: forcePublish,
            dry_run: false,
            cancel_active_execution: true,
        }),
        onSuccess: (data) => {
            setLastResult(data);
            setConfirming(false);
            if (data.ok)
                onCompleted?.();
        },
    });
    // Auto-dry-run al abrir el modal (con motivo placeholder), para enseñar al
    // operador las precondiciones antes de que escriba nada.
    useEffect(() => {
        if (open && !lastResult && !dryRunMutation.isPending) {
            dryRunMutation.mutate();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);
    const handleClose = useCallback(() => {
        setOpen(false);
        setReason("");
        setTargetState("");
        setPublishToAdo(true);
        setForcePublish(false);
        setLastResult(null);
        setConfirming(false);
    }, []);
    const reasonValid = reason.trim().length >= 5;
    const canConfirm = reasonValid && !finalMutation.isPending;
    const isBusy = dryRunMutation.isPending || finalMutation.isPending;
    return (_jsxs(_Fragment, { children: [_jsx("button", { className: styles.btn, onClick: (e) => { e.stopPropagation(); setOpen(true); }, disabled: disabled, title: disabled
                    ? "Hay un agente corriendo — esperá a que termine o cancelalo"
                    : "Forzar cierre manual del ticket (publica HTML del agente y cambia estado)", children: "\uD83C\uDFC1 Terminar trabajo" }), open && (_jsx("div", { className: styles.overlay, onClick: handleClose, children: _jsxs("div", { className: styles.modal, onClick: (e) => e.stopPropagation(), children: [_jsxs("header", { className: styles.header, children: [_jsx("h3", { className: styles.title, children: "Terminar trabajo manualmente" }), _jsx("button", { className: styles.close, onClick: handleClose, disabled: isBusy, children: "\u2715" })] }), _jsxs("div", { className: styles.sub, children: [_jsxs("span", { className: styles.adoTag, children: ["ADO-", ticket.ado_id] }), _jsx("span", { className: styles.ticketTitle, children: ticket.title })] }), _jsxs("section", { className: styles.section, children: [_jsx("h4", { className: styles.h4, children: "Precondiciones" }), dryRunMutation.isPending && (_jsx("p", { className: styles.muted, children: "Verificando estado\u2026" })), lastResult && (_jsxs("ul", { className: styles.preconds, children: [_jsxs("li", { children: [_jsx("span", { className: styles.checkLabel, children: "HTML del agente en disco:" }), " ", _jsx("span", { className: lastResult.preconditions.html_exists ? styles.ok : styles.warn, children: lastResult.preconditions.html_exists
                                                        ? "✓ presente"
                                                        : "✗ no encontrado (se publicará nota de cierre manual)" })] }), lastResult.preconditions.html_invalid_reason && (_jsxs("li", { children: [_jsx("span", { className: styles.checkLabel, children: "Motivo:" }), " ", _jsx("span", { className: styles.warn, children: lastResult.preconditions.html_invalid_reason })] })), _jsxs("li", { children: [_jsx("span", { className: styles.checkLabel, children: "stacky_status actual:" }), " ", _jsx("code", { children: lastResult.preconditions.current_stacky_status })] }), _jsxs("li", { children: [_jsx("span", { className: styles.checkLabel, children: "\u00DAltima ejecuci\u00F3n:" }), " ", lastResult.preconditions.execution_id !== null
                                                    ? _jsxs("code", { children: ["#", lastResult.preconditions.execution_id] })
                                                    : _jsx("span", { className: styles.warn, children: "ninguna" })] })] })), lastResult?.preconditions.active_execution && (_jsxs("p", { className: styles.activeExecWarning, children: ["Ejecucion activa: #", lastResult.preconditions.active_execution.execution_id, " ", "(", lastResult.preconditions.active_execution.agent_type, ") \u2014 se cancelara antes del cierre"] }))] }), _jsxs("section", { className: styles.section, children: [_jsxs("label", { className: styles.label, children: ["Motivo del cierre manual ", _jsx("span", { className: styles.req, children: "(obligatorio, min 5 chars)" })] }), _jsx("textarea", { className: styles.textarea, value: reason, onChange: (e) => setReason(e.target.value), placeholder: "Ej: El agente termin\u00F3 pero Stacky no recibi\u00F3 la se\u00F1al por timeout", rows: 3, disabled: isBusy, autoFocus: true }), _jsxs("label", { className: styles.inlineLabel, children: [_jsx("input", { type: "checkbox", checked: publishToAdo, onChange: (e) => setPublishToAdo(e.target.checked), disabled: isBusy }), " ", "Publicar comentario en ADO"] }), _jsxs("label", { className: styles.label, children: ["Estado destino en ADO ", _jsx("span", { className: styles.opt, children: "(opcional)" })] }), _jsx("input", { type: "text", className: styles.input, value: targetState, onChange: (e) => setTargetState(e.target.value), placeholder: "Ej: Done, Closed, Resolved", disabled: isBusy, list: "ado-state-suggestions" }), _jsxs("datalist", { id: "ado-state-suggestions", children: [_jsx("option", { value: "Done" }), _jsx("option", { value: "Closed" }), _jsx("option", { value: "Resolved" }), _jsx("option", { value: "Active" })] }), _jsxs("label", { className: styles.inlineLabel, children: [_jsx("input", { type: "checkbox", checked: forcePublish, onChange: (e) => setForcePublish(e.target.checked), disabled: isBusy }), " ", "Forzar re-publicaci\u00F3n (ignorar dedupe por hash)"] })] }), lastResult && !lastResult.dry_run && lastResult.actions.length > 0 && (_jsxs("section", { className: styles.section, children: [_jsx("h4", { className: styles.h4, children: "Resultado" }), _jsx("ul", { className: styles.actions, children: lastResult.actions.map((a, i) => (_jsxs("li", { className: a.ok ? styles.actionOk : styles.actionFail, children: [_jsx("span", { className: styles.actionIcon, children: a.ok ? "✓" : "✗" }), _jsx("span", { className: styles.actionName, children: a.action }), a.to && _jsx("code", { className: styles.actionTo, children: a.to }), a.reason && _jsx("span", { className: styles.actionReason, children: a.reason })] }, i))) }), lastResult.cancel_result != null && (lastResult.cancel_result.cancel_ok ? (_jsxs("p", { className: styles.cancelResultOk, children: ["Cancelacion: OK (ejecucion #", lastResult.cancel_result.execution_id, " ", "\u2014 ", lastResult.cancel_result.agent_type, ")"] })) : (_jsxs("p", { className: styles.cancelResultFail, children: ["Cancelacion fallo: ", lastResult.cancel_result.cancel_reason ?? "razon desconocida", ". El cierre se ejecuto igualmente."] })))] })), finalMutation.isError && (_jsxs("p", { className: styles.errorMsg, children: ["\u26A0 Error al ejecutar cierre: ", finalMutation.error?.message] })), dryRunMutation.isError && (_jsxs("p", { className: styles.errorMsg, children: ["\u26A0 Error al validar: ", dryRunMutation.error?.message] })), _jsxs("footer", { className: styles.footer, children: [_jsx("button", { className: styles.cancel, onClick: handleClose, disabled: isBusy, children: "Cerrar" }), !confirming ? (_jsx("button", { className: styles.danger, onClick: () => setConfirming(true), disabled: !canConfirm, title: !reasonValid
                                        ? "Ingresá un motivo de al menos 5 caracteres"
                                        : "Cerrar el ticket ahora", children: "\uD83C\uDFC1 Terminar trabajo" })) : (_jsx("button", { className: styles.dangerConfirm, onClick: () => finalMutation.mutate(), disabled: finalMutation.isPending, children: finalMutation.isPending
                                        ? "⏳ Procesando…"
                                        : "⚠ Confirmar cierre" }))] })] }) }))] }));
}
