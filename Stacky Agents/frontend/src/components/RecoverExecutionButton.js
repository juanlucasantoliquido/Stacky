import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * RecoverExecutionButton — Botón "Cerrar ejecución y publicar".
 *
 * Visible cuando un ticket está en estado INCONSISTENTE:
 *   ticket.stacky_status == 'completed' AND hay una ejecución huérfana
 *   con status in {running, queued}.
 *
 * Flujo (plan §7.1, §7.2, §7.3):
 *   1. Click → llama al gateway con force=false.
 *   2. 200 → invalidar cache + toast verde.
 *   3. 409 html_already_published → diálogo de confirmación force=true.
 *      - Acepta → reintentar con force=true.
 *      - Rechaza → cerrar sin hacer nada.
 *   4. Otros 409/422 → toast de error con copy mapeado.
 *   5. 401/500 → toast genérico + console.error (sin stacktrace al usuario).
 *
 * Diseño: sigue el tema existente del repo (sin librerías UI nuevas).
 */
import { useState, useCallback, useId } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AgentCompletion } from "../api/endpoints";
import { getErrorInfo } from "../utils/agentCompletionErrors";
import styles from "./RecoverExecutionButton.module.css";
function Toast({ toast, onClose }) {
    return (_jsxs("div", { className: `${styles.toast} ${styles[`toast_${toast.variant}`]}`, "data-correlation-id": toast.correlationId ?? undefined, role: "alert", "aria-live": "assertive", children: [_jsxs("div", { className: styles.toastHeader, children: [_jsx("strong", { className: styles.toastTitle, children: toast.title }), _jsx("button", { className: styles.toastClose, onClick: onClose, "aria-label": "Cerrar notificaci\u00F3n", children: "\u2715" })] }), _jsx("p", { className: styles.toastBody, children: toast.body })] }));
}
function ForceConfirmDialog({ onAccept, onReject, isBusy }) {
    return (_jsx("div", { className: styles.dialogOverlay, role: "dialog", "aria-modal": "true", "aria-labelledby": "force-dialog-title", children: _jsxs("div", { className: styles.dialog, children: [_jsx("h3", { id: "force-dialog-title", className: styles.dialogTitle, children: "HTML ya publicado" }), _jsx("p", { className: styles.dialogBody, children: "Ya existe un comentario publicado para esta ejecuci\u00F3n. Si continuas, se publicar\u00E1 el HTML actual en su lugar (forzado)." }), _jsx("p", { className: styles.dialogBody, style: { color: "rgba(255,255,255,0.5)", fontSize: 12, marginTop: 4 }, children: "Esta acci\u00F3n queda registrada en el audit log de Stacky." }), _jsxs("div", { className: styles.dialogActions, children: [_jsx("button", { className: styles.dialogCancel, onClick: onReject, disabled: isBusy, children: "Cancelar" }), _jsx("button", { className: styles.dialogConfirm, onClick: onAccept, disabled: isBusy, children: isBusy ? "Procesando..." : "Forzar publicación" })] })] }) }));
}
// ─── Componente principal ─────────────────────────────────────────────────────
export default function RecoverExecutionButton({ adoId, ticketId, orphanExecution, onRecovered, compact = false, }) {
    const qc = useQueryClient();
    const toastId = useId();
    const [isBusy, setIsBusy] = useState(false);
    const [toast, setToast] = useState(null);
    const [showForceDialog, setShowForceDialog] = useState(false);
    const dismissToast = useCallback(() => setToast(null), []);
    /**
     * Llama al gateway de agent-completion.
     * Devuelve true si el cierre fue exitoso (200), false en cualquier otro caso.
     */
    const callGateway = useCallback(async (force) => {
        const payload = {
            execution_id: orphanExecution.id,
            agent_type: orphanExecution.agent_type,
            status: "completed",
            html_output_path: orphanExecution.metadata?.html_output_path ?? null,
            metadata: {
                ...(orphanExecution.metadata ?? {}),
            },
            reason: "Recuperación manual desde UI",
            force,
        };
        const response = await AgentCompletion.complete(adoId, payload);
        if (response.ok && response.data) {
            // Éxito: invalidar cache y notificar al usuario
            qc.invalidateQueries({ queryKey: ["tickets"] });
            qc.invalidateQueries({ queryKey: ["tickets-hierarchy"] });
            qc.invalidateQueries({ queryKey: ["executions-active"] });
            qc.invalidateQueries({ queryKey: ["executions-queued"] });
            qc.invalidateQueries({ queryKey: ["ticket-detail", ticketId] });
            setToast({
                variant: "success",
                title: "Ejecución cerrada",
                body: `La ejecución fue cerrada y publicada correctamente. (${response.data.result ?? "ok"})`,
                correlationId: response.data.correlation_id,
            });
            onRecovered?.();
            return true;
        }
        // Manejo de errores
        const code = response.errorBody?.error ?? "";
        const correlationId = response.errorBody?.correlation_id;
        if (response.status === 409 && code === "html_already_published") {
            // Este caso lo maneja el caller para mostrar el diálogo force
            return false;
        }
        // Errores conocidos mapeados a copy
        const info = getErrorInfo(code);
        if (response.status === 401 || response.status === 500) {
            // Error genérico para auth y errores internos — solo log a consola
            console.error("[RecoverExecution] Gateway error", {
                status: response.status,
                code,
                correlationId,
                body: response.errorBody,
            });
        }
        setToast({
            variant: info.severity === "error" ? "error" : "warning",
            title: info.title,
            body: info.body,
            correlationId,
        });
        return false;
    }, [adoId, ticketId, orphanExecution, qc, onRecovered]);
    const handleClick = useCallback(async () => {
        if (isBusy)
            return;
        setIsBusy(true);
        setToast(null);
        try {
            const response = await AgentCompletion.complete(adoId, {
                execution_id: orphanExecution.id,
                agent_type: orphanExecution.agent_type,
                status: "completed",
                html_output_path: orphanExecution.metadata?.html_output_path ?? null,
                metadata: { ...(orphanExecution.metadata ?? {}) },
                reason: "Recuperación manual desde UI",
                force: false,
            });
            if (response.ok && response.data) {
                qc.invalidateQueries({ queryKey: ["tickets"] });
                qc.invalidateQueries({ queryKey: ["tickets-hierarchy"] });
                qc.invalidateQueries({ queryKey: ["executions-active"] });
                qc.invalidateQueries({ queryKey: ["executions-queued"] });
                qc.invalidateQueries({ queryKey: ["ticket-detail", ticketId] });
                setToast({
                    variant: "success",
                    title: "Ejecución cerrada",
                    body: `La ejecución fue cerrada y publicada. (${response.data.result ?? "ok"})`,
                    correlationId: response.data.correlation_id,
                });
                onRecovered?.();
                return;
            }
            const code = response.errorBody?.error ?? "";
            const correlationId = response.errorBody?.correlation_id;
            if (response.status === 409 && code === "html_already_published") {
                // Mostrar diálogo de confirmación force=true
                setShowForceDialog(true);
                return;
            }
            if (response.status === 401 || response.status === 500) {
                console.error("[RecoverExecution] Gateway error", {
                    status: response.status,
                    code,
                    correlationId,
                    body: response.errorBody,
                });
            }
            const info = getErrorInfo(code);
            setToast({
                variant: info.severity === "error" ? "error" : "warning",
                title: info.title,
                body: info.body,
                correlationId,
            });
        }
        finally {
            setIsBusy(false);
        }
    }, [adoId, ticketId, orphanExecution, qc, onRecovered, isBusy]);
    const handleForceAccept = useCallback(async () => {
        setIsBusy(true);
        try {
            await callGateway(true);
        }
        finally {
            setIsBusy(false);
            setShowForceDialog(false);
        }
    }, [callGateway]);
    const handleForceReject = useCallback(() => {
        setShowForceDialog(false);
    }, []);
    return (_jsxs(_Fragment, { children: [_jsx("button", { className: `${styles.recoverBtn} ${compact ? styles.recoverBtnCompact : ""}`, onClick: handleClick, disabled: isBusy, title: "Cerrar la ejecuci\u00F3n hu\u00E9rfana y publicar en ADO", "aria-label": "Cerrar ejecuci\u00F3n y publicar", children: isBusy
                    ? (compact ? "..." : "Procesando...")
                    : (compact ? "Recuperar" : "Cerrar ejecución y publicar") }), showForceDialog && (_jsx(ForceConfirmDialog, { onAccept: handleForceAccept, onReject: handleForceReject, isBusy: isBusy })), toast && _jsx(Toast, { toast: toast, onClose: dismissToast })] }));
}
