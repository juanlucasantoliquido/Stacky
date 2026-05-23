import { jsxs as _jsxs, jsx as _jsx, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * CreateChildTaskButton — Crear Tasks hijas en ADO desde pending-task.json (Fase 2).
 *
 * Visible en el card de un Epic cuando hay pending-task.json pendientes en
 * Agentes/outputs/epic-{ado_id}/.
 *
 * Flujo:
 *   1. Fetch de GET /api/tickets/by-ado/{epicAdoId}/pending-tasks al montar.
 *   2. Si total_pending=0 → no se renderiza el botón.
 *   3. Click → modal con lista de RFs pendientes.
 *   4. Operador selecciona RFs, escribe motivo, confirma.
 *   5. Por cada RF seleccionado → POST /api/tickets/by-ado/{epicAdoId}/create-child-task.
 *   6. Muestra resultado por RF (ok / parcial / error).
 *   7. Toast final con resumen. Invalida queries de tickets/hierarchy.
 *
 * Diseño: sigue el patrón de FinishWorkButton (modal, A11y, sin librerías UI extra).
 */
import { useState, useCallback, useId } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Tickets, } from "../api/endpoints";
import styles from "./CreateChildTaskButton.module.css";
// ─── Componente ───────────────────────────────────────────────────────────────
export default function CreateChildTaskButton({ epicAdoId, disabled, onTaskCreated, }) {
    const qc = useQueryClient();
    const modalId = useId();
    const [open, setOpen] = useState(false);
    const [selected, setSelected] = useState(new Set());
    const [reason, setReason] = useState("");
    const [dryRun, setDryRun] = useState(false);
    const [rfResults, setRfResults] = useState([]);
    const [isRunning, setIsRunning] = useState(false);
    const [toast, setToast] = useState(null);
    // ── Fetch de pending-tasks ─────────────────────────────────────────────────
    const { data: pendingData, isError: fetchError } = useQuery({
        queryKey: ["pending-tasks", epicAdoId],
        queryFn: () => Tickets.listPendingTasks(epicAdoId),
        staleTime: 60_000,
        refetchOnWindowFocus: false,
        enabled: true,
    });
    const totalPending = pendingData?.total_pending ?? 0;
    const pendingTasks = pendingData?.pending_tasks ?? [];
    // ── Handlers ──────────────────────────────────────────────────────────────
    // IMPORTANT: todos los hooks (incluidos los useCallback de abajo) deben
    // ejecutarse en TODOS los renders. Los early returns van AL FINAL, justo
    // antes del JSX, para no violar las Rules of Hooks.
    const handleOpen = useCallback((e) => {
        e.stopPropagation();
        setOpen(true);
        setSelected(new Set(pendingTasks.map((t) => t.rf_id)));
        setRfResults([]);
        setToast(null);
    }, [pendingTasks]);
    const handleClose = useCallback(() => {
        if (isRunning)
            return;
        setOpen(false);
        setReason("");
        setDryRun(false);
        setSelected(new Set());
        setRfResults([]);
    }, [isRunning]);
    const toggleSelect = useCallback((rfId) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(rfId))
                next.delete(rfId);
            else
                next.add(rfId);
            return next;
        });
    }, []);
    const handleCreate = useCallback(async () => {
        if (isRunning || selected.size === 0)
            return;
        const tasksToRun = pendingTasks.filter((t) => selected.has(t.rf_id));
        setRfResults(tasksToRun.map((t) => ({ rf_id: t.rf_id, title: t.title, status: "pending" })));
        setIsRunning(true);
        let createdCount = 0;
        let errorCount = 0;
        for (const task of tasksToRun) {
            setRfResults((prev) => prev.map((r) => (r.rf_id === task.rf_id ? { ...r, status: "running" } : r)));
            try {
                const resp = await Tickets.createChildTask(epicAdoId, {
                    pending_task_path: task.pending_task_path,
                    operator_reason: reason.trim() || undefined,
                    dry_run: dryRun,
                });
                let status = "ok";
                if (resp.idempotent)
                    status = "idempotent";
                else if (!resp.ok && resp.task_ado_id)
                    status = "partial";
                else if (!resp.ok)
                    status = "error";
                if (resp.ok || resp.task_ado_id)
                    createdCount++;
                else
                    errorCount++;
                setRfResults((prev) => prev.map((r) => r.rf_id === task.rf_id ? { ...r, status, response: resp } : r));
            }
            catch (err) {
                errorCount++;
                setRfResults((prev) => prev.map((r) => r.rf_id === task.rf_id
                    ? { ...r, status: "error", error: err.message }
                    : r));
            }
        }
        setIsRunning(false);
        // Invalidar queries
        qc.invalidateQueries({ queryKey: ["pending-tasks", epicAdoId] });
        qc.invalidateQueries({ queryKey: ["tickets"] });
        qc.invalidateQueries({ queryKey: ["tickets-hierarchy"] });
        // Toast resumen
        if (errorCount === 0) {
            setToast({ ok: true, message: `${createdCount} Task(s) creada(s) en ADO exitosamente.` });
            if (createdCount > 0)
                onTaskCreated?.();
        }
        else {
            setToast({
                ok: false,
                message: `${createdCount} ok, ${errorCount} con error. Revisar resultados.`,
            });
        }
    }, [epicAdoId, isRunning, selected, pendingTasks, reason, dryRun, qc, onTaskCreated]);
    const canCreate = selected.size > 0 && !isRunning;
    // ── Early returns (DESPUÉS de todos los hooks) ────────────────────────────
    // No renderizar si no hay pendientes (y no hay error de fetch)
    if (!fetchError && totalPending === 0 && pendingData !== undefined) {
        return null;
    }
    // Si hay error de fetch, no mostramos el botón tampoco (sin crashear el árbol)
    if (fetchError && pendingData === undefined) {
        return null;
    }
    // ── Render ────────────────────────────────────────────────────────────────
    return (_jsxs(_Fragment, { children: [_jsxs("button", { className: styles.btn, onClick: handleOpen, disabled: disabled || totalPending === 0, title: totalPending === 0
                    ? "No hay Tasks pendientes de crear"
                    : `Crear ${totalPending} Task(s) hija(s) en ADO`, "aria-label": `Crear Tasks en ADO (${totalPending} pendiente${totalPending !== 1 ? "s" : ""})`, children: ["Crear Tasks en ADO (", totalPending, " pendiente", totalPending !== 1 ? "s" : "", ")"] }), open && (_jsx("div", { className: styles.overlay, onClick: handleClose, role: "dialog", "aria-modal": "true", "aria-labelledby": `${modalId}-title`, children: _jsxs("div", { className: styles.modal, onClick: (e) => e.stopPropagation(), children: [_jsxs("header", { className: styles.header, children: [_jsx("h3", { id: `${modalId}-title`, className: styles.title, children: "Crear Tasks en ADO" }), _jsx("button", { className: styles.close, onClick: handleClose, disabled: isRunning, "aria-label": "Cerrar modal", children: "\u2715" })] }), _jsxs("div", { style: { display: "flex", gap: 8, alignItems: "center", marginTop: 8 }, children: [_jsxs("span", { className: styles.epicTag, children: ["EPIC-", epicAdoId] }), _jsxs("span", { className: styles.muted, children: [totalPending, " RF(s) pendiente(s) de crear en ADO"] })] }), _jsxs("section", { className: styles.section, children: [_jsx("h4", { className: styles.h4, children: "Requisitos funcionales pendientes" }), _jsx("ul", { className: styles.rfList, role: "list", children: pendingTasks.map((task) => {
                                        const result = rfResults.find((r) => r.rf_id === task.rf_id);
                                        return (_jsxs("li", { className: styles.rfItem, children: [_jsx("input", { type: "checkbox", id: `rf-${task.rf_id}`, checked: selected.has(task.rf_id), onChange: () => toggleSelect(task.rf_id), disabled: isRunning || !!result, "aria-label": task.rf_id }), _jsxs("label", { htmlFor: `rf-${task.rf_id}`, className: styles.rfInfo, style: { cursor: "pointer" }, children: [_jsx("div", { className: styles.rfId, children: task.rf_id }), _jsx("div", { className: styles.rfTitle, children: task.title }), _jsxs("div", { className: styles.rfMeta, children: ["Plan:", " ", task.plan_exists
                                                                    ? _jsx("span", { className: styles.rfPlanOk, children: "presente" })
                                                                    : _jsx("span", { className: styles.rfPlanMissing, children: "no encontrado \u2014 se omitira el adjunto" })] })] }), result && (_jsxs("span", { style: { fontSize: 11, fontWeight: 700 }, children: [result.status === "running" && _jsx("span", { style: { color: "#60a5fa" }, children: "..." }), result.status === "ok" && _jsx("span", { style: { color: "#4ade80" }, children: "OK" }), result.status === "idempotent" && _jsx("span", { style: { color: "#a78bfa" }, children: "YA EXISTIA" }), result.status === "partial" && _jsx("span", { style: { color: "#fbbf24" }, children: "PARCIAL" }), result.status === "error" && _jsx("span", { style: { color: "#f87171" }, children: "ERROR" })] }))] }, task.rf_id));
                                    }) })] }), _jsxs("section", { className: styles.section, children: [_jsxs("label", { className: styles.label, children: ["Motivo del operador ", _jsx("span", { className: styles.opt, children: "(opcional)" })] }), _jsx("textarea", { className: styles.textarea, value: reason, onChange: (e) => setReason(e.target.value), placeholder: "Ej: Revisado con el equipo t\u00E9cnico, listo para an\u00E1lisis", rows: 2, disabled: isRunning }), _jsxs("label", { className: styles.inlineLabel, children: [_jsx("input", { type: "checkbox", checked: dryRun, onChange: (e) => setDryRun(e.target.checked), disabled: isRunning }), " ", "Dry run \u2014 solo validar, no crear en ADO"] })] }), rfResults.length > 0 && (_jsxs("section", { className: styles.section, children: [_jsx("h4", { className: styles.h4, children: "Resultados" }), _jsx("ul", { className: styles.results, children: rfResults.map((r) => (_jsxs("li", { className: r.status === "ok" || r.status === "idempotent"
                                            ? styles.resultOk
                                            : r.status === "partial"
                                                ? styles.resultWarn
                                                : r.status === "error"
                                                    ? styles.resultFail
                                                    : undefined, children: [_jsxs("div", { children: [_jsx("strong", { children: r.rf_id }), r.status === "running" && " — procesando...", r.status === "ok" && r.response?.task_url && (_jsxs(_Fragment, { children: [" — Task ", _jsxs("a", { href: r.response.task_url, target: "_blank", rel: "noopener noreferrer", className: styles.resultLink, children: ["ADO-", r.response.task_ado_id] }), " creada"] })), r.status === "idempotent" && r.response?.task_url && (_jsxs(_Fragment, { children: [" — ya existia: ", _jsxs("a", { href: r.response.task_url, target: "_blank", rel: "noopener noreferrer", className: styles.resultLink, children: ["ADO-", r.response.task_ado_id] })] })), r.status === "partial" && ` — Task ADO-${r.response?.task_ado_id} creada, adjunto falló`, r.status === "error" && ` — Error: ${r.error ?? r.response?.message ?? "desconocido"}`] }), r.response?.human_action_required && (_jsx("div", { className: styles.humanAction, children: r.response.human_action_required }))] }, r.rf_id))) })] })), toast && (_jsx("div", { role: "alert", "aria-live": "assertive", className: toast.ok ? styles.resultOk : styles.errorMsg, style: { padding: "8px 10px", borderRadius: 4, fontSize: 12, marginTop: 8 }, children: toast.message })), _jsxs("footer", { className: styles.footer, children: [_jsx("button", { className: styles.cancel, onClick: handleClose, disabled: isRunning, children: rfResults.length > 0 ? "Cerrar" : "Cancelar" }), _jsx("button", { className: styles.primary, onClick: handleCreate, disabled: !canCreate, "aria-label": dryRun ? "Simular creación (dry run)" : "Crear Task en ADO", children: isRunning
                                        ? "Procesando..."
                                        : dryRun
                                            ? "Simular (dry run)"
                                            : `Crear Task en ADO (${selected.size})` })] })] }) }))] }));
}
