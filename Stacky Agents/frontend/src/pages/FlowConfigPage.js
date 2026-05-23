import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * FlowConfigPage — Feature #4 (SDD-2026-05-19)
 *
 * Administración del mapeo determinístico ado_state → agent_type.
 * Permite listar, crear, editar inline y eliminar reglas.
 * Errores del backend (409 duplicado, 400 validación) se muestran inline.
 *
 * VALID_AGENT_TYPES: business | functional | technical | developer | qa
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FlowConfig, Projects } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./FlowConfigPage.module.css";
const VALID_AGENT_TYPES = ["business", "functional", "technical", "developer", "qa"];
const AGENT_LABELS = {
    business: "Business",
    functional: "Functional",
    technical: "Technical",
    developer: "Developer",
    qa: "QA",
};
// ── helpers ──────────────────────────────────────────────────────────────────
function extractErrorMessage(err) {
    if (!err)
        return "Error desconocido";
    if (typeof err === "object" && err !== null) {
        const e = err;
        if (typeof e.message === "string")
            return e.message;
        if (typeof e.detail === "string")
            return e.detail;
        if (typeof e.error === "string")
            return e.error;
        // FastAPI/httpx response pattern
        const data = e.data;
        if (data && typeof data.message === "string")
            return data.message;
        if (data && typeof data.detail === "string")
            return data.detail;
    }
    return String(err);
}
function CreateForm({ onCreated, trackerStates, loadingStates, usedStates, activeProjectName }) {
    const availableStates = trackerStates.filter((s) => !usedStates.has(s));
    const [adoState, setAdoState] = useState(availableStates[0] ?? "");
    const [agentType, setAgentType] = useState("business");
    const [error, setError] = useState(null);
    const qc = useQueryClient();
    // Mantener el select sincronizado con la lista filtrada si cambia (ej. al crear/borrar reglas).
    if (adoState && !availableStates.includes(adoState) && availableStates.length > 0) {
        setAdoState(availableStates[0]);
    }
    if (!adoState && availableStates.length > 0) {
        setAdoState(availableStates[0]);
    }
    const mutation = useMutation({
        mutationFn: () => FlowConfig.create({
            ado_state: adoState.trim(),
            agent_type: agentType,
            project: activeProjectName,
        }),
        onSuccess: () => {
            setAdoState("");
            setAgentType("business");
            setError(null);
            qc.invalidateQueries({ queryKey: ["flow-config", activeProjectName] });
            onCreated();
        },
        onError: (err) => {
            setError(extractErrorMessage(err));
        },
    });
    const noProject = !activeProjectName;
    const noStates = !loadingStates && trackerStates.length === 0;
    const allUsed = !loadingStates && trackerStates.length > 0 && availableStates.length === 0;
    const canSubmit = adoState.trim().length > 0 && !mutation.isPending && !noProject && !noStates && !allUsed;
    return (_jsxs("div", { className: styles.formCard, children: [_jsx("p", { className: styles.formTitle, children: "Nueva regla" }), _jsxs("div", { className: styles.formRow, children: [_jsxs("div", { className: styles.fieldGroup, children: [_jsx("label", { className: styles.label, htmlFor: "fc-ado-state", children: "Estado ADO" }), _jsxs("select", { id: "fc-ado-state", className: styles.select, value: adoState, onChange: (e) => { setAdoState(e.target.value); setError(null); }, disabled: noProject || loadingStates || noStates || allUsed, children: [loadingStates && _jsx("option", { value: "", children: "Cargando estados\u2026" }), !loadingStates && noProject && _jsx("option", { value: "", children: "Sin proyecto activo" }), !loadingStates && noStates && _jsx("option", { value: "", children: "No hay estados disponibles" }), !loadingStates && allUsed && _jsx("option", { value: "", children: "Todos los estados ya tienen regla" }), !loadingStates && availableStates.map((s) => (_jsx("option", { value: s, children: s }, s)))] })] }), _jsxs("div", { className: styles.fieldGroup, children: [_jsx("label", { className: styles.label, htmlFor: "fc-agent-type", children: "Tipo de agente" }), _jsx("select", { id: "fc-agent-type", className: styles.select, value: agentType, onChange: (e) => setAgentType(e.target.value), children: VALID_AGENT_TYPES.map((t) => (_jsx("option", { value: t, children: AGENT_LABELS[t] }, t))) })] }), _jsx("button", { className: styles.btnPrimary, onClick: () => mutation.mutate(), disabled: !canSubmit, children: mutation.isPending ? "Guardando..." : "Agregar" })] }), error && _jsx("div", { className: styles.errorBanner, children: error })] }));
}
function RuleRow({ rule, trackerStates, otherUsedStates, activeProjectName }) {
    const [editing, setEditing] = useState(false);
    const [editAdoState, setEditAdoState] = useState(rule.ado_state);
    const [editAgentType, setEditAgentType] = useState(VALID_AGENT_TYPES.includes(rule.agent_type)
        ? rule.agent_type
        : "business");
    const [error, setError] = useState(null);
    const qc = useQueryClient();
    const updateMutation = useMutation({
        mutationFn: () => FlowConfig.update(rule.id, {
            ado_state: editAdoState.trim(),
            agent_type: editAgentType,
            project: activeProjectName,
        }),
        onSuccess: () => {
            setEditing(false);
            setError(null);
            qc.invalidateQueries({ queryKey: ["flow-config", activeProjectName] });
        },
        onError: (err) => {
            setError(extractErrorMessage(err));
        },
    });
    const deleteMutation = useMutation({
        mutationFn: () => FlowConfig.delete(rule.id, activeProjectName),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["flow-config", activeProjectName] });
        },
        onError: (err) => {
            setError(extractErrorMessage(err));
        },
    });
    const handleCancelEdit = () => {
        setEditing(false);
        setEditAdoState(rule.ado_state);
        setEditAgentType(VALID_AGENT_TYPES.includes(rule.agent_type)
            ? rule.agent_type
            : "business");
        setError(null);
    };
    const isLoading = updateMutation.isPending || deleteMutation.isPending;
    if (editing) {
        // Opciones disponibles: estados del tracker que no estén ocupados por OTRAS reglas
        // + el estado actual de esta regla (para no autoexcluirse).
        const selectableStates = trackerStates.filter((s) => !otherUsedStates.has(s) || s === rule.ado_state);
        // Si el estado actual no está en el tracker (por ejemplo, regla creada antes del dropdown),
        // lo incluimos como opción para permitir editarlo sin perderlo.
        if (!selectableStates.includes(editAdoState) && editAdoState) {
            selectableStates.unshift(editAdoState);
        }
        return (_jsxs(_Fragment, { children: [_jsxs("tr", { className: `${styles.tr} ${styles.trEditing}`, children: [_jsx("td", { className: styles.td, children: _jsxs("select", { className: styles.inlineSelect, value: editAdoState, onChange: (e) => { setEditAdoState(e.target.value); setError(null); }, autoFocus: true, children: [selectableStates.length === 0 && _jsx("option", { value: "", children: "Sin estados disponibles" }), selectableStates.map((s) => (_jsx("option", { value: s, children: s }, s)))] }) }), _jsx("td", { className: styles.td, children: _jsx("select", { className: styles.inlineSelect, value: editAgentType, onChange: (e) => setEditAgentType(e.target.value), children: VALID_AGENT_TYPES.map((t) => (_jsx("option", { value: t, children: AGENT_LABELS[t] }, t))) }) }), _jsx("td", { className: styles.td, style: { color: "rgba(255,255,255,0.3)", fontSize: 11 }, children: new Date(rule.updated_at).toLocaleDateString() }), _jsxs("td", { className: styles.tdActions, children: [_jsx("button", { className: styles.btnIcon, onClick: () => updateMutation.mutate(), disabled: isLoading || editAdoState.trim().length === 0, title: "Guardar", children: updateMutation.isPending ? "..." : "Guardar" }), _jsx("button", { className: styles.btnIcon, onClick: handleCancelEdit, disabled: isLoading, title: "Cancelar", children: "Cancelar" })] })] }), error && (_jsx("tr", { children: _jsx("td", { colSpan: 4, className: styles.td, children: _jsx("div", { className: styles.errorBanner, children: error }) }) }))] }));
    }
    return (_jsxs("tr", { className: styles.tr, children: [_jsx("td", { className: styles.td, children: rule.ado_state }), _jsx("td", { className: styles.td, children: _jsx("span", { className: styles.badge, children: rule.agent_type }) }), _jsx("td", { className: styles.td, style: { color: "rgba(255,255,255,0.3)", fontSize: 11 }, children: new Date(rule.updated_at).toLocaleDateString() }), _jsxs("td", { className: styles.tdActions, children: [_jsx("button", { className: styles.btnIcon, onClick: () => setEditing(true), disabled: isLoading, title: "Editar", children: "Editar" }), _jsx("button", { className: `${styles.btnIcon} ${styles.btnIconDanger}`, onClick: () => {
                            if (window.confirm(`Eliminar regla "${rule.ado_state} → ${rule.agent_type}"?`)) {
                                deleteMutation.mutate();
                            }
                        }, disabled: isLoading, title: "Eliminar", children: deleteMutation.isPending ? "..." : "Eliminar" })] })] }));
}
// ── main page ─────────────────────────────────────────────────────────────────
export default function FlowConfigPage() {
    const activeProject = useWorkbench((s) => s.activeProject);
    const activeProjectName = activeProject?.name ?? null;
    const { data, isLoading, error } = useQuery({
        queryKey: ["flow-config", activeProjectName],
        queryFn: () => FlowConfig.list(activeProjectName),
        staleTime: 30_000,
    });
    const trackerStatesQuery = useQuery({
        queryKey: ["tracker-states", activeProject?.name],
        queryFn: () => Projects.trackerStates(activeProject.name),
        enabled: !!activeProject,
        staleTime: 5 * 60_000,
    });
    const rules = data?.rules ?? [];
    const trackerStates = trackerStatesQuery.data?.states ?? [];
    const usedStates = new Set(rules.map((r) => r.ado_state));
    return (_jsxs("div", { className: styles.root, children: [_jsxs("div", { className: styles.header, children: [_jsx("h2", { className: styles.title, children: "Config de Flujo" }), _jsxs("p", { className: styles.subtitle, children: ["Mapeo determin\u00EDstico: estado ADO \u2192 tipo de agente sugerido. Clave usada: ", _jsx("code", { children: "agent_type" }), "."] })] }), !activeProject && (_jsx("div", { className: styles.empty, style: { marginBottom: 16 }, children: "Sin proyecto activo. Seleccion\u00E1 un proyecto en el TopBar para ver los estados ADO disponibles." })), _jsx(CreateForm, { onCreated: () => { }, trackerStates: trackerStates, loadingStates: trackerStatesQuery.isLoading, usedStates: usedStates, activeProjectName: activeProjectName }), _jsxs("div", { className: styles.tableCard, children: [_jsxs("div", { className: styles.tableHeader, children: [_jsx("span", { className: styles.tableTitle, children: "Reglas activas" }), _jsxs("span", { className: styles.tableCount, children: [rules.length, " regla", rules.length !== 1 ? "s" : ""] })] }), isLoading && _jsx("div", { className: styles.loading, children: "Cargando..." }), error && (_jsxs("div", { className: styles.empty, children: ["Error al cargar reglas: ", extractErrorMessage(error)] })), !isLoading && !error && rules.length === 0 && (_jsx("div", { className: styles.empty, children: "No hay reglas configuradas. Agrega una arriba." })), !isLoading && !error && rules.length > 0 && (_jsxs("table", { className: styles.table, children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { className: styles.th, children: "Estado ADO" }), _jsx("th", { className: styles.th, children: "Tipo de agente" }), _jsx("th", { className: styles.th, children: "Actualizado" }), _jsx("th", { className: styles.th, style: { textAlign: "right" }, children: "Acciones" })] }) }), _jsx("tbody", { children: rules.map((rule) => {
                                    const otherUsedStates = new Set(rules.filter((r) => r.id !== rule.id).map((r) => r.ado_state));
                                    return (_jsx(RuleRow, { rule: rule, trackerStates: trackerStates, otherUsedStates: otherUsedStates, activeProjectName: activeProjectName }, rule.id));
                                }) })] }))] })] }));
}
