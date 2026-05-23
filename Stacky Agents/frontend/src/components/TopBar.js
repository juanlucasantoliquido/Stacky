import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect, useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWorkbench } from "../store/workbench";
import { Projects } from "../api/endpoints";
import NewProjectModal from "./NewProjectModal";
import EditProjectModal from "./EditProjectModal";
import styles from "./TopBar.module.css";
export default function TopBar({ onGoToTeam }) {
    const runningExecutionId = useWorkbench((s) => s.runningExecutionId);
    const isRunning = runningExecutionId != null;
    const setActiveProject = useWorkbench((s) => s.setActiveProject);
    const setPinnedAgents = useWorkbench((s) => s.setPinnedAgents);
    const setAgentWorkflows = useWorkbench((s) => s.setAgentWorkflows);
    const setTeamLoading = useWorkbench((s) => s.setTeamLoading);
    const setGetAgentsError = useWorkbench((s) => s.setGetAgentsError);
    const queryClient = useQueryClient();
    /** Contador incremental para detectar y descartar respuestas de requests anteriores. */
    const loadSeq = useRef(0);
    const [projects, setProjects] = useState([]);
    const [activeProjectName, setActiveProjectName] = useState("");
    const [newProjectOpen, setNewProjectOpen] = useState(false);
    const [editProjectOpen, setEditProjectOpen] = useState(false);
    const activeProject = projects.find((p) => p.name === activeProjectName) ?? null;
    /** Carga los agentes fijados de un proyecto y los mete en el store. */
    const loadProjectAgents = useCallback(async (name) => {
        const seq = ++loadSeq.current;
        setTeamLoading(true);
        setGetAgentsError(null);
        // Limpiar estado del proyecto anterior inmediatamente
        setPinnedAgents([]);
        setAgentWorkflows({});
        try {
            const res = await Projects.getAgents(name);
            if (seq !== loadSeq.current)
                return; // request obsoleta — ignorar
            const agents = res.pinned_agents ?? [];
            setPinnedAgents(agents);
            // Cargar workflow de cada agente y guardar en store
            const wfMap = {};
            await Promise.all(agents.map(async (filename) => {
                try {
                    const wf = await Projects.getAgentWorkflow(name, filename);
                    if (wf.ok) {
                        wfMap[filename] = {
                            allowed_states: wf.allowed_states ?? [],
                            transition_state: wf.transition_state ?? "",
                            requires_prior_output: wf.requires_prior_output ?? false,
                        };
                    }
                }
                catch { /* ignore workflow individual */ }
            }));
            if (seq !== loadSeq.current)
                return; // cambio de proyecto mientras cargaba workflows
            setAgentWorkflows(wfMap);
        }
        catch {
            if (seq !== loadSeq.current)
                return;
            setPinnedAgents([]);
            setAgentWorkflows({});
            setGetAgentsError("No se pudieron cargar los empleados del proyecto. Reintentá o revisá logs.");
        }
        finally {
            if (seq === loadSeq.current)
                setTeamLoading(false);
        }
    }, [setPinnedAgents, setAgentWorkflows, setTeamLoading, setGetAgentsError]);
    async function loadProjects() {
        try {
            const res = await Projects.list();
            setProjects(res.projects ?? []);
            const active = (res.projects ?? []).find((p) => p.active);
            if (active) {
                setActiveProjectName(active.name);
                setActiveProject(active);
                await loadProjectAgents(active.name);
            }
        }
        catch {
            // ignore
        }
    }
    useEffect(() => { loadProjects(); }, []);
    async function handleProjectChange(name) {
        setActiveProjectName(name);
        try {
            const res = await Projects.setActive(name);
            if (res.project)
                setActiveProject(res.project);
            await loadProjectAgents(name);
            // Limpiar caches sensibles al proyecto para no mostrar datos viejos
            queryClient.removeQueries({ queryKey: ["tickets"] });
            queryClient.removeQueries({ queryKey: ["tickets-hierarchy"] });
            queryClient.removeQueries({ queryKey: ["flow-config"] });
            queryClient.removeQueries({ queryKey: ["ticket-sync"] });
            queryClient.removeQueries({ queryKey: ["executions-active"] });
            queryClient.removeQueries({ queryKey: ["executions-queued"] });
            queryClient.invalidateQueries({ queryKey: ["vscode-agents"] });
        }
        catch {
            // ignore
        }
    }
    function handleProjectCreated(name, _displayName) {
        loadProjects();
        handleProjectChange(name);
    }
    async function handleDeleteProject(name) {
        if (!window.confirm(`¿Eliminar el proyecto "${name}"? Esta acción no se puede deshacer.`))
            return;
        try {
            await Projects.remove(name);
            await loadProjects();
        }
        catch (e) {
            window.alert(`Error al eliminar: ${e?.message || e}`);
        }
    }
    return (_jsxs("header", { className: styles.bar, children: [_jsxs("div", { className: styles.main, children: [_jsxs("div", { className: styles.brand, children: [onGoToTeam && (_jsx("button", { className: styles.teamBtn, onClick: onGoToTeam, title: "Volver al equipo", children: "\u2190 Equipo" })), _jsx("img", { src: "/stacky-logo.svg", alt: "Stacky", className: styles.logoImg, width: 22, height: 22 }), "Stacky"] }), _jsxs("div", { className: styles.project, children: [_jsx("span", { className: styles.projectLabel, children: "Proyecto" }), projects.length > 0 ? (_jsx("select", { className: styles.projectSelect, value: activeProjectName, onChange: (e) => handleProjectChange(e.target.value), children: projects.map((p) => (_jsxs("option", { value: p.name, children: [p.display_name || p.name, p.has_credentials === false ? " ⚠" : ""] }, p.name))) })) : (_jsx("strong", { className: styles.projectFallback, children: "Sin proyectos" })), activeProject && (_jsx("button", { className: styles.editProjectBtn, title: "Editar proyecto activo", onClick: () => setEditProjectOpen(true), children: "\u270E" })), _jsx("button", { className: styles.newProjectBtn, title: "Inicializar nuevo proyecto", onClick: () => setNewProjectOpen(true), children: "+" })] }), _jsxs("div", { className: styles.actions, children: [isRunning && (_jsxs("span", { className: styles.runningBadge, children: [_jsx("span", { className: styles.badgeSpinner, "aria-hidden": "true" }), "Agente trabajando\u2026"] })), _jsx("span", { children: "dev@local" })] })] }), isRunning && _jsx("div", { className: styles.progressBar, role: "progressbar", "aria-label": "Ejecuci\u00F3n en progreso" }), newProjectOpen && (_jsx(NewProjectModal, { onClose: () => setNewProjectOpen(false), onCreated: handleProjectCreated })), editProjectOpen && activeProject && (_jsx(EditProjectModal, { project: activeProject, onClose: () => setEditProjectOpen(false), onSaved: () => { setEditProjectOpen(false); loadProjects(); }, onDelete: () => { setEditProjectOpen(false); handleDeleteProject(activeProject.name); } }))] }));
}
