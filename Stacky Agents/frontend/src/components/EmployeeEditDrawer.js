import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect } from "react";
import { getAgentAvatar, setAgentAvatar, getAgentNickname, setAgentNickname, getAgentRole, setAgentRole, getAgentType, setAgentType, } from "../services/preferences";
const VALID_AGENT_TYPES = [
    "business",
    "functional",
    "technical",
    "developer",
    "qa",
];
// Heurística usada cuando el operador no fijó un tipo explícito.
function inferTypeFromFilename(filename) {
    const f = filename.toLowerCase();
    if (f.includes("business") || f.includes("negocio"))
        return "business";
    if (f.includes("functional") || f.includes("funcional"))
        return "functional";
    if (f.includes("technical") || f.includes("tecnico") || f.includes("técnico"))
        return "technical";
    if (f.includes("dev") || f.includes("developer"))
        return "developer";
    if (f.includes("qa") || f.includes("test"))
        return "qa";
    return "";
}
import { Projects } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import AgentWorkflowForm from "./AgentWorkflowForm";
import AvatarPicker from "./AvatarPicker";
import PixelAvatar from "./PixelAvatar";
import styles from "./EmployeeEditDrawer.module.css";
export default function EmployeeEditDrawer({ filename, agent, onClose, onRemoved }) {
    const defaultName = agent?.name ?? filename.replace(/\.agent\.md$/i, "");
    const defaultRole = agent?.description?.split(".")[0] ?? "Agente VS Code";
    const [nickname, setNickname] = useState(getAgentNickname(filename) ?? "");
    const [role, setRole] = useState(getAgentRole(filename) ?? "");
    const [avatar, setAvatar] = useState(getAgentAvatar(filename));
    const [agentTypeValue, setAgentTypeValue] = useState(getAgentType(filename) ?? "");
    const inferredType = inferTypeFromFilename(filename);
    const [confirmRemove, setConfirmRemove] = useState(false);
    // Workflow config
    const activeProject = useWorkbench((s) => s.activeProject);
    const setAgentWorkflows = useWorkbench((s) => s.setAgentWorkflows);
    const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
    const [trackerStates, setTrackerStates] = useState([]);
    const [trackerLoadError, setTrackerLoadError] = useState(false);
    const [loadingTrackerStates, setLoadingTrackerStates] = useState(false);
    const [workflow, setWorkflow] = useState({
        allowed_states: [],
        transition_state: "",
        requires_prior_output: false,
    });
    const [savingWf, setSavingWf] = useState(false);
    const [wfSaved, setWfSaved] = useState(false);
    useEffect(() => {
        if (!activeProject)
            return;
        // Cargar estados del tracker
        setLoadingTrackerStates(true);
        setTrackerLoadError(false);
        Projects.trackerStates(activeProject.name)
            .then((r) => { if (r.ok)
            setTrackerStates(r.states ?? []); })
            .catch(() => setTrackerLoadError(true))
            .finally(() => setLoadingTrackerStates(false));
        // Cargar workflow actual del agente
        Projects.getAgentWorkflow(activeProject.name, filename)
            .then((r) => {
            if (r.ok) {
                setWorkflow({
                    allowed_states: r.allowed_states ?? [],
                    transition_state: r.transition_state ?? "",
                    requires_prior_output: r.requires_prior_output ?? false,
                });
            }
        })
            .catch(() => { });
    }, [activeProject, filename]);
    async function handleSaveWorkflow() {
        if (!activeProject)
            return;
        setSavingWf(true);
        try {
            await Projects.putAgentWorkflow(activeProject.name, filename, {
                allowed_states: workflow.allowed_states,
                transition_state: workflow.transition_state,
                requires_prior_output: workflow.requires_prior_output,
            });
            // Actualizar store
            setAgentWorkflows({
                ...agentWorkflows,
                [filename]: {
                    allowed_states: workflow.allowed_states,
                    transition_state: workflow.transition_state,
                    requires_prior_output: workflow.requires_prior_output,
                },
            });
            setWfSaved(true);
            setTimeout(() => setWfSaved(false), 2000);
        }
        catch { /* ignore */ }
        finally {
            setSavingWf(false);
        }
    }
    function handleSave() {
        if (avatar)
            setAgentAvatar(filename, avatar);
        setAgentNickname(filename, nickname.trim() || defaultName);
        setAgentRole(filename, role.trim() || defaultRole);
        setAgentType(filename, agentTypeValue);
        onClose();
    }
    function handleRemove() {
        // Membresía persiste vía Projects.putAgents — el padre maneja el remove.
        onRemoved();
    }
    return (_jsx("div", { className: styles.overlay, onClick: (e) => e.target === e.currentTarget && onClose(), children: _jsxs("div", { className: styles.drawer, children: [_jsxs("div", { className: styles.header, children: [_jsx(PixelAvatar, { value: avatar, size: "md", name: nickname || defaultName }), _jsxs("div", { className: styles.headerText, children: [_jsx("h2", { className: styles.title, children: "Editar empleado" }), _jsx("span", { className: styles.filename, children: filename })] }), _jsx("button", { className: styles.closeBtn, onClick: onClose, title: "Cerrar", children: "\u2715" })] }), _jsxs("div", { className: styles.body, children: [_jsxs("div", { className: styles.field, children: [_jsx("label", { className: styles.label, children: "Apodo" }), _jsx("input", { className: styles.input, type: "text", placeholder: defaultName, value: nickname, onChange: (e) => setNickname(e.target.value) })] }), _jsxs("div", { className: styles.field, children: [_jsx("label", { className: styles.label, children: "Rol" }), _jsx("input", { className: styles.input, type: "text", placeholder: defaultRole, value: role, onChange: (e) => setRole(e.target.value) })] }), _jsxs("div", { className: styles.field, children: [_jsx("label", { className: styles.label, children: "Tipo de agente" }), _jsxs("select", { className: styles.input, value: agentTypeValue, onChange: (e) => setAgentTypeValue(e.target.value), children: [_jsx("option", { value: "", children: inferredType
                                                ? `Auto (${inferredType})`
                                                : "Auto (sin detectar)" }), VALID_AGENT_TYPES.map((t) => (_jsx("option", { value: t, children: t }, t)))] }), _jsx("span", { style: { fontSize: 11, color: "var(--text-faint)", marginTop: 4, display: "block" }, children: "Usado por \"Config de Flujo\" para resolver el agente sugerido por estado ADO." })] }), _jsxs("div", { className: styles.field, children: [_jsx("label", { className: styles.label, children: "Avatar" }), _jsx(AvatarPicker, { value: avatar, onChange: (v) => setAvatar(v) })] }), activeProject && (_jsxs("div", { className: styles.field, children: [_jsxs("label", { className: styles.label, children: ["\u2699\uFE0F Workflow", _jsx("span", { style: { fontWeight: 400, fontSize: 11, color: "var(--text-faint)", marginLeft: 8 }, children: activeProject.display_name ?? activeProject.name })] }), _jsx(AgentWorkflowForm, { value: workflow, onChange: setWorkflow, trackerStates: trackerStates, loadingStates: loadingTrackerStates, loadError: trackerLoadError, projectDisplayName: activeProject.display_name ?? activeProject.name }), _jsx("button", { type: "button", className: styles.saveBtn, style: { marginTop: 10, fontSize: 13 }, onClick: handleSaveWorkflow, disabled: savingWf || !activeProject, children: savingWf ? "Guardando…" : wfSaved ? "✓ Guardado" : "💾 Guardar configuración de estados" })] }))] }), _jsxs("div", { className: styles.footer, children: [confirmRemove ? (_jsxs("div", { className: styles.confirmRow, children: [_jsx("span", { className: styles.confirmText, children: "\u00BFQuitar del equipo?" }), _jsx("button", { className: styles.cancelBtn, onClick: () => setConfirmRemove(false), children: "No" }), _jsx("button", { className: styles.dangerBtn, onClick: handleRemove, children: "S\u00ED, quitar" })] })) : (_jsx("button", { className: styles.removeBtn, onClick: () => setConfirmRemove(true), children: "\uD83D\uDDD1\uFE0F Quitar del equipo" })), _jsxs("div", { className: styles.mainActions, children: [_jsx("button", { className: styles.cancelBtn, onClick: onClose, children: "Cancelar" }), _jsx("button", { className: styles.saveBtn, onClick: handleSave, children: "Guardar" })] })] })] }) }));
}
