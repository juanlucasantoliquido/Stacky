import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from "react";
import { getAgentAvatar, setAgentAvatar, getAgentNickname, setAgentNickname, getAgentRole, setAgentRole, } from "../services/preferences";
import { Projects } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import AgentWorkflowForm from "./AgentWorkflowForm";
import PixelAvatar from "./PixelAvatar";
import AvatarPicker from "./AvatarPicker";
import styles from "./TeamManageDrawer.module.css";
export default function TeamManageDrawer({ allAgents, onClose }) {
    // ─── Fuente de verdad: store por proyecto ──────────────────────────────────
    const activeProject = useWorkbench((s) => s.activeProject);
    const pinned = useWorkbench((s) => s.pinnedAgents);
    const setPinnedAgents = useWorkbench((s) => s.setPinnedAgents);
    const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
    const setAgentWorkflows = useWorkbench((s) => s.setAgentWorkflows);
    const [pendingAdd, setPendingAdd] = useState(null);
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState(null);
    // ─── Workflow state para el modal de alta ─────────────────────────────
    const [pendingWorkflow, setPendingWorkflow] = useState({
        allowed_states: [],
        transition_state: "",
        requires_prior_output: false,
    });
    const [trackerStates, setTrackerStates] = useState([]);
    const [loadingTrackerStates, setLoadingTrackerStates] = useState(false);
    const [trackerLoadError, setTrackerLoadError] = useState(false);
    // true = agent ya persistió, sólo faltó el workflow
    const [agentAlreadySaved, setAgentAlreadySaved] = useState(false);
    // Close config modal with Escape
    useEffect(() => {
        if (!pendingAdd)
            return;
        const handler = (e) => { if (e.key === "Escape")
            handleCancelModal(); };
        window.addEventListener("keydown", handler);
        return () => window.removeEventListener("keydown", handler);
    }, [pendingAdd]);
    function isInTeam(filename) {
        return pinned.includes(filename);
    }
    function handleCancelModal() {
        if (!agentAlreadySaved)
            setPendingAdd(null);
        else
            setPendingAdd(null); // permite cerrar aunque el agente ya fue guardado
        setAgentAlreadySaved(false);
        setSaveError(null);
    }
    async function handleSelectForAdd(agent) {
        if (!activeProject || saving)
            return;
        if (isInTeam(agent.filename)) {
            const nextPinned = pinned.filter((f) => f !== agent.filename);
            setSaving(true);
            setSaveError(null);
            try {
                await Projects.putAgents(activeProject.name, nextPinned);
                setPinnedAgents(nextPinned);
            }
            catch {
                setSaveError("No se pudo guardar el equipo del proyecto. Reintentá o revisá logs.");
            }
            finally {
                setSaving(false);
            }
            return;
        }
        // Resetear estado del modal
        setPendingWorkflow({ allowed_states: [], transition_state: "", requires_prior_output: false });
        setAgentAlreadySaved(false);
        setSaveError(null);
        setPendingAdd({
            filename: agent.filename,
            agentName: agent.name,
            avatar: getAgentAvatar(agent.filename),
            nickname: getAgentNickname(agent.filename) ?? "",
            role: getAgentRole(agent.filename) ?? "",
        });
        // Cargar tracker states en paralelo
        if (activeProject) {
            setLoadingTrackerStates(true);
            setTrackerLoadError(false);
            Projects.trackerStates(activeProject.name)
                .then((r) => { if (r.ok)
                setTrackerStates(r.states ?? []); })
                .catch(() => setTrackerLoadError(true))
                .finally(() => setLoadingTrackerStates(false));
        }
    }
    async function handleConfirmAdd() {
        if (!pendingAdd || !activeProject || saving)
            return;
        setSaving(true);
        setSaveError(null);
        // Paso 1: persistir membresía (saltar si ya se guardó en intento anterior)
        if (!agentAlreadySaved) {
            if (pendingAdd.avatar)
                setAgentAvatar(pendingAdd.filename, pendingAdd.avatar);
            if (pendingAdd.nickname.trim())
                setAgentNickname(pendingAdd.filename, pendingAdd.nickname.trim());
            if (pendingAdd.role.trim())
                setAgentRole(pendingAdd.filename, pendingAdd.role.trim());
            const nextPinned = pinned.includes(pendingAdd.filename)
                ? pinned
                : [...pinned, pendingAdd.filename];
            try {
                await Projects.putAgents(activeProject.name, nextPinned);
                setPinnedAgents(nextPinned);
                setAgentAlreadySaved(true);
            }
            catch {
                setSaveError("No se pudo guardar el equipo del proyecto. Reintentá o revisá logs.");
                setSaving(false);
                return;
            }
        }
        // Paso 2: persistir workflow
        try {
            const wf = {
                allowed_states: pendingWorkflow.allowed_states,
                transition_state: pendingWorkflow.transition_state,
                requires_prior_output: pendingWorkflow.requires_prior_output,
            };
            await Projects.putAgentWorkflow(activeProject.name, pendingAdd.filename, wf);
            setAgentWorkflows({ ...agentWorkflows, [pendingAdd.filename]: wf });
            // Éxito total: cerrar modal
            setPendingAdd(null);
            setAgentAlreadySaved(false);
        }
        catch {
            setSaveError("El empleado se agregó, pero no se pudo guardar su workflow. ¡Comletá el workflow antes de usarlo.");
        }
        finally {
            setSaving(false);
        }
    }
    return (_jsxs(_Fragment, { children: [_jsx("div", { className: styles.overlay, onClick: (e) => e.target === e.currentTarget && onClose(), children: _jsxs("div", { className: styles.drawer, children: [_jsxs("div", { className: styles.header, children: [_jsx("h2", { className: styles.title, children: "Agentes disponibles en VS Code" }), _jsx("button", { className: styles.closeBtn, onClick: onClose, title: "Cerrar", children: "\u2715" })] }), _jsxs("p", { className: styles.hint, children: ["\uD83D\uDCC1 Fuente: ", _jsx("code", { children: "%APPDATA%/Code/User/prompts" })] }), !activeProject && (_jsx("div", { className: styles.empty, children: "Seleccion\u00E1 un proyecto activo antes de agregar o quitar empleados." })), saveError && (_jsxs("div", { className: styles.errorBanner, role: "alert", children: ["\u26A0 ", saveError] })), allAgents.length === 0 ? (_jsx("div", { className: styles.empty, children: "No se encontraron agentes. Verific\u00E1 que VS Code est\u00E9 corriendo con la extensi\u00F3n Stacky." })) : (_jsx("div", { className: styles.list, children: allAgents.map((agent) => {
                                const inTeam = isInTeam(agent.filename);
                                const avatar = getAgentAvatar(agent.filename);
                                return (_jsxs("div", { className: inTeam ? styles.agentRowDone : styles.agentRow, children: [_jsx(PixelAvatar, { value: avatar, size: "sm", name: agent.name }), _jsxs("div", { className: styles.agentInfo, children: [_jsx("span", { className: styles.agentName, children: agent.name }), _jsx("span", { className: styles.agentDesc, children: agent.description?.slice(0, 80) ?? agent.filename })] }), inTeam && _jsx("span", { className: styles.inTeamBadge, children: "\u2713" }), _jsx("button", { className: inTeam ? styles.removeBtn : styles.addBtn, onClick: () => handleSelectForAdd(agent), disabled: saving || !activeProject, children: saving && inTeam ? "Guardando…" : inTeam ? "Quitar" : "+ Agregar" })] }, agent.filename));
                            }) })), _jsx("div", { className: styles.footer, children: _jsx("button", { className: styles.doneBtn, onClick: onClose, children: "Listo" }) })] }) }), pendingAdd && (_jsx("div", { className: styles.modalBackdrop, onClick: (e) => e.target === e.currentTarget && handleCancelModal(), children: _jsxs("div", { className: styles.modal, role: "dialog", "aria-modal": "true", children: [_jsx("div", { className: styles.modalAvatar, children: _jsx(PixelAvatar, { value: pendingAdd.avatar, size: "lg", name: pendingAdd.agentName }) }), _jsx("h3", { className: styles.modalAgentName, children: pendingAdd.agentName }), _jsx("p", { className: styles.modalSubtitle, children: "Personaliz\u00E1 tu nuevo empleado" }), !agentAlreadySaved && (_jsxs(_Fragment, { children: [_jsxs("div", { className: styles.modalFields, children: [_jsxs("div", { className: styles.modalField, children: [_jsx("label", { className: styles.modalLabel, children: "Apodo" }), _jsx("input", { className: styles.modalInput, placeholder: pendingAdd.agentName, value: pendingAdd.nickname, onChange: (e) => setPendingAdd({ ...pendingAdd, nickname: e.target.value }), autoFocus: true })] }), _jsxs("div", { className: styles.modalField, children: [_jsx("label", { className: styles.modalLabel, children: "Rol" }), _jsx("input", { className: styles.modalInput, placeholder: "ej: Analista Senior", value: pendingAdd.role, onChange: (e) => setPendingAdd({ ...pendingAdd, role: e.target.value }) })] })] }), _jsxs("div", { className: styles.modalPickerSection, children: [_jsx("label", { className: styles.modalLabel, children: "Avatar" }), _jsx(AvatarPicker, { value: pendingAdd.avatar, onChange: (v) => setPendingAdd({ ...pendingAdd, avatar: v }) })] })] })), _jsxs("div", { className: styles.modalWorkflowSection, children: [_jsx("p", { className: styles.modalLabel, children: "\u2699\uFE0F Configuraci\u00F3n de workflow" }), _jsx(AgentWorkflowForm, { value: pendingWorkflow, onChange: setPendingWorkflow, trackerStates: trackerStates, loadingStates: loadingTrackerStates, loadError: trackerLoadError, projectDisplayName: activeProject?.display_name ?? activeProject?.name })] }), saveError && (_jsxs("div", { className: styles.errorBanner, role: "alert", children: ["\u26A0 ", saveError] })), _jsxs("div", { className: styles.modalActions, children: [_jsx("button", { className: styles.modalCancelBtn, onClick: handleCancelModal, disabled: saving, children: agentAlreadySaved ? "Cerrar" : "Cancelar" }), _jsx("button", { className: styles.modalConfirmBtn, onClick: handleConfirmAdd, disabled: saving, children: saving
                                        ? "Guardando…"
                                        : agentAlreadySaved
                                            ? "↺ Reintentar workflow"
                                            : "✓ Agregar al equipo" })] })] }) }))] }));
}
