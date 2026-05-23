import { jsxs as _jsxs, jsx as _jsx, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from "react";
import { Projects, Mantis } from "../api/endpoints";
import styles from "./NewProjectModal.module.css";
export default function EditProjectModal({ project, onClose, onSaved, onDelete }) {
    const [form, setForm] = useState({
        display_name: project.display_name,
        workspace_root: project.workspace_root,
        docs_technical_path: project.docs_paths?.technical ?? project.docs_technical_path ?? "",
        docs_functional_path: project.docs_paths?.functional ?? project.docs_functional_path ?? "",
        docs_paths: project.docs_paths ?? { technical: "", functional: "" },
        tracker_type: project.tracker_type,
        organization: project.organization ?? "",
        ado_project: project.ado_project ?? "",
        pat: "",
        jira_url: project.jira_url ?? "",
        jira_key: project.jira_key ?? "",
        api_version: "3",
        jql: "",
        verify_ssl: true,
        jira_user: "",
        jira_token: "",
        mantis_url: project.mantis_url ?? "",
        mantis_project_id: project.mantis_project_id ?? "",
        mantis_project_name: project.mantis_project_name ?? "",
        mantis_protocol: (project.mantis_protocol ?? "rest"),
        mantis_token: "",
        mantis_username: "",
        mantis_password: "",
    });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const [loadedUser, setLoadedUser] = useState(null);
    const [docsChecking, setDocsChecking] = useState(false);
    const [docsCheckMessage, setDocsCheckMessage] = useState(null);
    // Mantis: listar proyectos disponibles
    const [mantisProjects, setMantisProjects] = useState([]);
    const [mantisLoading, setMantisLoading] = useState(false);
    const [mantisLoadError, setMantisLoadError] = useState(null);
    // Workflow por agente
    const [pinnedAgents, setPinnedAgents] = useState([]);
    const [trackerStates, setTrackerStates] = useState([]);
    const [workflows, setWorkflows] = useState({});
    const [savingWorkflow, setSavingWorkflow] = useState(null);
    // Carga el usuario guardado para mostrarlo en el placeholder
    useEffect(() => {
        Projects.getCredentials(project.name)
            .then((res) => {
            if (res.ok) {
                if (res.jira_user) {
                    setLoadedUser(res.jira_user);
                    setForm((f) => ({ ...f, jira_user: res.jira_user ?? "" }));
                }
                // Para Mantis: si hay project_id y protocol guardado en auth, los usamos
                if (res.mantis_project_id) {
                    setForm((f) => ({ ...f, mantis_project_id: res.mantis_project_id ?? "" }));
                }
                if (res.mantis_protocol) {
                    setForm((f) => ({ ...f, mantis_protocol: (res.mantis_protocol ?? "rest") }));
                }
            }
        })
            .catch(() => { });
        // Cargar agentes fijados
        Projects.getAgents(project.name)
            .then((res) => { if (res.ok)
            setPinnedAgents(res.pinned_agents ?? []); })
            .catch(() => { });
        // Cargar estados del tracker
        Projects.trackerStates(project.name)
            .then((res) => { if (res.ok)
            setTrackerStates(res.states ?? []); })
            .catch(() => { });
    }, [project.name]);
    // Cargar workflow de cada agente fijado
    useEffect(() => {
        if (pinnedAgents.length === 0)
            return;
        pinnedAgents.forEach((filename) => {
            Projects.getAgentWorkflow(project.name, filename)
                .then((res) => {
                if (res.ok) {
                    setWorkflows((prev) => ({
                        ...prev,
                        [filename]: {
                            allowed_states: res.allowed_states ?? [],
                            transition_state: res.transition_state ?? "",
                            requires_prior_output: res.requires_prior_output ?? false,
                        },
                    }));
                }
            })
                .catch(() => { });
        });
    }, [project.name, pinnedAgents]);
    function patchWorkflow(filename, key, value) {
        setWorkflows((prev) => ({
            ...prev,
            [filename]: { ...(prev[filename] ?? { allowed_states: [], transition_state: "", requires_prior_output: false }), [key]: value },
        }));
    }
    async function saveWorkflow(filename) {
        const wf = workflows[filename];
        if (!wf)
            return;
        setSavingWorkflow(filename);
        try {
            await Projects.putAgentWorkflow(project.name, filename, wf);
        }
        catch { /* ignore */ }
        finally {
            setSavingWorkflow(null);
        }
    }
    async function loadMantisProjects() {
        const url = (form.mantis_url || "").trim();
        const protocol = form.mantis_protocol || "rest";
        const token = (form.mantis_token || "").trim();
        const username = (form.mantis_username || "").trim();
        const password = (form.mantis_password || "").trim();
        if (!url) {
            setMantisLoadError("Ingresá la URL de Mantis antes de cargar proyectos.");
            return;
        }
        if (protocol === "soap") {
            if (!username && !project.has_credentials) {
                setMantisLoadError("Ingresá el usuario de Mantis para SOAP.");
                return;
            }
        }
        else {
            if (!token && !project.has_credentials) {
                setMantisLoadError("Ingresá el token de Mantis antes de cargar proyectos.");
                return;
            }
        }
        setMantisLoading(true);
        setMantisLoadError(null);
        try {
            const params = { url, protocol, verify_ssl: form.verify_ssl !== false };
            if (protocol === "soap") {
                params.username = username;
                params.password = password;
            }
            else {
                params.token = token;
            }
            const res = await Mantis.listProjects(params);
            if (res.ok) {
                setMantisProjects(res.projects);
                if (res.projects.length === 0)
                    setMantisLoadError("No se encontraron proyectos accesibles.");
            }
            else {
                setMantisLoadError(res.error || "Error al conectar con Mantis");
            }
        }
        catch (e) {
            setMantisLoadError(e?.message || "Error de conexión");
        }
        finally {
            setMantisLoading(false);
        }
    }
    function patch(key, value) {
        setForm((f) => ({ ...f, [key]: value }));
        if (key === "docs_technical_path" || key === "docs_functional_path") {
            setDocsCheckMessage(null);
        }
    }
    function buildPayload() {
        const docs_paths = {
            technical: String(form.docs_technical_path ?? "").trim(),
            functional: String(form.docs_functional_path ?? "").trim(),
        };
        return { ...form, docs_paths };
    }
    async function browseDocsPath(kind) {
        setError(null);
        const currentPath = kind === "technical" ? form.docs_technical_path : form.docs_functional_path;
        try {
            const res = await Projects.browseFolder({
                title: kind === "technical" ? "Seleccionar documentación técnica" : "Seleccionar documentación funcional / manual",
                initial_dir: String(currentPath || form.workspace_root || ""),
            });
            if (res.ok && res.path) {
                patch(kind === "technical" ? "docs_technical_path" : "docs_functional_path", res.path);
            }
            else if (!res.ok) {
                setError(res.error || "No se pudo abrir el selector de carpeta");
            }
        }
        catch (e) {
            setError(e?.message || "No se pudo abrir el selector de carpeta");
        }
    }
    async function testDocsPaths() {
        setError(null);
        setDocsCheckMessage(null);
        const payload = buildPayload();
        if (!payload.docs_paths?.technical && !payload.docs_paths?.functional) {
            setDocsCheckMessage("Sin rutas configuradas: Stacky usará autodiscovery en workspace_root/docs.");
            return;
        }
        setDocsChecking(true);
        try {
            const res = await Projects.testDocsPaths(project.name, payload);
            const tech = res.counts.technical;
            const functional = res.counts.functional;
            setDocsCheckMessage(`Técnica: ${tech.total} archivos (${tech.md} .md, ${tech.pdf} .pdf). ` +
                `Funcional: ${functional.total} archivos (${functional.md} .md, ${functional.pdf} .pdf).`);
        }
        catch (e) {
            setError(e?.message || "No se pudieron validar las rutas de documentación");
        }
        finally {
            setDocsChecking(false);
        }
    }
    const isAdo = form.tracker_type === "azure_devops";
    const isJira = form.tracker_type === "jira";
    const isMantis = form.tracker_type === "mantis";
    async function handleSubmit() {
        setError(null);
        if (!String(form.workspace_root ?? "").trim()) {
            setError("Ingresá el workspace root");
            return;
        }
        setSaving(true);
        try {
            const res = await Projects.update(project.name, buildPayload());
            if (res.ok) {
                onSaved();
            }
            else {
                setError(res.error || "Error desconocido");
            }
        }
        catch (e) {
            setError(e?.message || "Error de conexión");
        }
        finally {
            setSaving(false);
        }
    }
    return (_jsx("div", { className: styles.backdrop, onClick: (e) => { if (e.target === e.currentTarget)
            onClose(); }, children: _jsxs("div", { className: styles.panel, children: [_jsxs("h2", { className: styles.title, children: ["\u270E Editar Proyecto: ", project.display_name || project.name] }), _jsxs("div", { className: styles.body, children: [_jsx("label", { className: styles.label, children: "Nombre para mostrar" }), _jsx("input", { className: styles.input, type: "text", value: form.display_name ?? "", onChange: (e) => patch("display_name", e.target.value) }), _jsx("label", { className: styles.label, children: "Workspace root" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: C:\\Repos\\MiProyecto\\trunk", value: form.workspace_root ?? "", onChange: (e) => patch("workspace_root", e.target.value) }), _jsxs("div", { className: styles.docsPathSection, children: [_jsx("span", { className: styles.trackerHeading, children: "Documentaci\u00F3n del proyecto (opcional)" }), _jsxs("p", { className: styles.note, children: ["Estas rutas reemplazan el autodiscovery de ", _jsx("code", { children: "docs/" }), " para el panel Docs."] }), _jsx("label", { className: styles.label, children: "Documentaci\u00F3n t\u00E9cnica" }), _jsxs("div", { className: styles.pathRow, children: [_jsx("input", { className: styles.input, type: "text", placeholder: "Ej: C:\\Docs\\MiProyecto\\tecnica", value: form.docs_technical_path ?? "", onChange: (e) => patch("docs_technical_path", e.target.value) }), _jsx("button", { type: "button", className: styles.btnPath, onClick: () => browseDocsPath("technical"), children: "Examinar..." })] }), _jsx("label", { className: styles.label, children: "Documentaci\u00F3n funcional / manual" }), _jsxs("div", { className: styles.pathRow, children: [_jsx("input", { className: styles.input, type: "text", placeholder: "Ej: C:\\Docs\\MiProyecto\\funcional", value: form.docs_functional_path ?? "", onChange: (e) => patch("docs_functional_path", e.target.value) }), _jsx("button", { type: "button", className: styles.btnPath, onClick: () => browseDocsPath("functional"), children: "Examinar..." })] }), _jsxs("div", { className: styles.docsActions, children: [_jsx("button", { type: "button", className: styles.btnLoadProjects, onClick: testDocsPaths, disabled: docsChecking, children: docsChecking ? "Validando..." : "Probar rutas docs" }), docsCheckMessage && _jsx("span", { className: styles.docsCheckOk, children: docsCheckMessage })] })] }), _jsx("hr", { className: styles.divider }), _jsx("label", { className: styles.label, children: "Sistema de tickets" }), _jsxs("div", { className: styles.trackerRow, children: [_jsx("button", { type: "button", className: `${styles.trackerBtn} ${isAdo ? styles.trackerBtnActive : ""}`, onClick: () => patch("tracker_type", "azure_devops"), children: "\uD83D\uDD37 Azure DevOps" }), _jsx("button", { type: "button", className: `${styles.trackerBtn} ${isJira ? styles.trackerBtnJira : ""}`, onClick: () => patch("tracker_type", "jira"), children: "\uD83D\uDD35 Jira" }), _jsx("button", { type: "button", className: `${styles.trackerBtn} ${isMantis ? styles.trackerBtnMantis : ""}`, onClick: () => patch("tracker_type", "mantis"), children: "\uD83D\uDFE2 Mantis BT" })] }), isAdo && (_jsxs("div", { className: styles.trackerFields, children: [_jsx("span", { className: styles.trackerHeading, children: "\uD83D\uDD37 Azure DevOps" }), _jsx("label", { className: styles.label, children: "Organizaci\u00F3n ADO" }), _jsx("input", { className: styles.input, type: "text", value: form.organization ?? "", onChange: (e) => patch("organization", e.target.value) }), _jsx("label", { className: styles.label, children: "Proyecto ADO" }), _jsx("input", { className: styles.input, type: "text", value: form.ado_project ?? "", onChange: (e) => patch("ado_project", e.target.value) }), _jsx("label", { className: styles.label, children: "Personal Access Token (PAT)" }), _jsx("input", { className: styles.input, type: "password", placeholder: project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Pegá tu PAT de Azure DevOps", value: form.pat ?? "", onChange: (e) => patch("pat", e.target.value) }), _jsxs("details", { className: styles.advanced, children: [_jsx("summary", { children: "\uD83D\uDD0D Opciones avanzadas ADO" }), _jsxs("div", { className: styles.advancedBody, children: [_jsx("label", { className: styles.labelSm, children: "Area Path (opcional)" }), _jsx("input", { className: styles.input, type: "text", value: form.area_path ?? "", onChange: (e) => patch("area_path", e.target.value) })] })] })] })), isJira && (_jsxs("div", { className: styles.trackerFields, children: [_jsx("span", { className: `${styles.trackerHeading} ${styles.trackerHeadingJira}`, children: "\uD83D\uDD35 Jira" }), _jsx("label", { className: styles.label, children: "URL de la instancia Jira" }), _jsx("input", { className: styles.input, type: "text", value: form.jira_url ?? "", onChange: (e) => patch("jira_url", e.target.value) }), _jsx("label", { className: styles.label, children: "Clave del proyecto" }), _jsx("input", { className: styles.input, type: "text", value: form.jira_key ?? "", onChange: (e) => patch("jira_key", e.target.value) }), _jsx("label", { className: styles.label, children: "Usuario / Email" }), _jsx("input", { className: styles.input, type: "text", placeholder: loadedUser ? `${loadedUser} (usuario actual)` : "usuario@empresa.com", value: form.jira_user ?? "", onChange: (e) => patch("jira_user", e.target.value) }), _jsx("label", { className: styles.label, children: "API Token" }), _jsx("input", { className: styles.input, type: "password", placeholder: project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Pegá tu API token de Jira", value: form.jira_token ?? "", onChange: (e) => patch("jira_token", e.target.value) })] })), isMantis && (_jsxs("div", { className: styles.trackerFields, children: [_jsx("span", { className: `${styles.trackerHeading} ${styles.trackerHeadingMantis}`, children: "\uD83D\uDFE2 Mantis Bug Tracker" }), _jsx("label", { className: styles.label, children: "Protocolo de conexi\u00F3n" }), _jsxs("div", { className: styles.trackerRow, children: [_jsx("button", { type: "button", className: `${styles.trackerBtn} ${form.mantis_protocol !== "soap" ? styles.trackerBtnActive : ""}`, onClick: () => { patch("mantis_protocol", "rest"); setMantisProjects([]); setMantisLoadError(null); }, children: "\uD83D\uDD11 REST (Token API)" }), _jsx("button", { type: "button", className: `${styles.trackerBtn} ${form.mantis_protocol === "soap" ? styles.trackerBtnActive : ""}`, onClick: () => { patch("mantis_protocol", "soap"); setMantisProjects([]); setMantisLoadError(null); }, children: "\uD83D\uDD0C SOAP (Usuario/Contrase\u00F1a)" })] }), _jsx("label", { className: styles.label, children: "URL de la instancia Mantis" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: https://mantis.empresa.com", value: form.mantis_url ?? "", onChange: (e) => patch("mantis_url", e.target.value) }), form.mantis_protocol === "soap" ? (_jsxs(_Fragment, { children: [_jsx("label", { className: styles.label, children: "Usuario de Mantis" }), _jsx("input", { className: styles.input, type: "text", placeholder: project.has_credentials ? "••••  (dejar vacío para no cambiar)" : "Usuario de Mantis", value: form.mantis_username ?? "", onChange: (e) => patch("mantis_username", e.target.value) }), _jsx("label", { className: styles.label, children: "Contrase\u00F1a" }), _jsx("input", { className: styles.input, type: "password", placeholder: project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Contraseña de Mantis", value: form.mantis_password ?? "", onChange: (e) => patch("mantis_password", e.target.value) })] })) : (_jsxs(_Fragment, { children: [_jsx("label", { className: styles.label, children: "API Token" }), _jsx("input", { className: styles.input, type: "password", placeholder: project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Token de API de Mantis", value: form.mantis_token ?? "", onChange: (e) => patch("mantis_token", e.target.value) })] })), _jsx("button", { type: "button", className: styles.btnLoadProjects, onClick: loadMantisProjects, disabled: mantisLoading, children: mantisLoading ? "Cargando proyectos…" : "🔄 Cargar proyectos de Mantis" }), mantisLoadError && (_jsx("div", { className: styles.errorSmall, children: mantisLoadError })), mantisProjects.length > 0 && (_jsxs(_Fragment, { children: [_jsx("label", { className: styles.label, children: "Proyecto Mantis" }), _jsxs("select", { className: styles.select, value: form.mantis_project_id ?? "", onChange: (e) => {
                                                const selected = mantisProjects.find((p) => p.id === e.target.value);
                                                patch("mantis_project_id", e.target.value);
                                                patch("mantis_project_name", selected?.name ?? "");
                                            }, children: [_jsx("option", { value: "", children: "\u2014 Seleccion\u00E1 un proyecto \u2014" }), mantisProjects.map((p) => (_jsxs("option", { value: p.id, children: ["#", p.id, " \u2014 ", p.name, p.description ? ` (${p.description.slice(0, 40)})` : ""] }, p.id)))] })] })), !mantisProjects.length && (form.mantis_project_id || form.mantis_project_name) && (_jsxs("p", { className: styles.note, children: ["Proyecto actual: ", _jsx("strong", { children: form.mantis_project_name || `#${form.mantis_project_id}` }), " — ", "Carg\u00E1 proyectos para cambiar la selecci\u00F3n."] }))] })), error && _jsx("div", { className: styles.error, children: error }), pinnedAgents.length > 0 && (_jsxs(_Fragment, { children: [_jsx("hr", { className: styles.divider }), _jsx("span", { className: styles.trackerHeading, children: "\u2699\uFE0F Workflow por agente" }), _jsx("p", { style: { fontSize: 12, color: "var(--text-muted, #999)", marginTop: 4, marginBottom: 12 }, children: "Configur\u00E1 qu\u00E9 estados puede ver cada agente, a qu\u00E9 estado debe mover el ticket al terminar, y si requiere output anterior." }), pinnedAgents.map((filename) => {
                                    const wf = workflows[filename] ?? { allowed_states: [], transition_state: "", requires_prior_output: false };
                                    const label = filename.replace(/\.agent\.md$/i, "").replace(/_/g, " ");
                                    return (_jsxs("details", { className: styles.advanced, style: { marginBottom: 8 }, children: [_jsxs("summary", { style: { fontWeight: 600, cursor: "pointer" }, children: ["\uD83E\uDD16 ", label] }), _jsxs("div", { className: styles.advancedBody, children: [_jsx("label", { className: styles.labelSm, children: "Estados visibles (allowed_states)" }), _jsxs("p", { style: { fontSize: 11, color: "var(--text-muted, #999)", margin: "2px 0 6px" }, children: ["Estados del tracker que este agente puede procesar. Uno por l\u00EDnea.", trackerStates.length > 0 && (_jsxs(_Fragment, { children: [" Disponibles: ", _jsx("strong", { children: trackerStates.join(", ") })] }))] }), _jsx("textarea", { className: styles.input, rows: 3, style: { resize: "vertical", fontFamily: "monospace", fontSize: 12 }, value: wf.allowed_states.join("\n"), onChange: (e) => patchWorkflow(filename, "allowed_states", e.target.value.split("\n").map((s) => s.trim()).filter(Boolean)) }), _jsx("label", { className: styles.labelSm, style: { marginTop: 8 }, children: "Estado de transici\u00F3n (transition_state)" }), _jsx("p", { style: { fontSize: 11, color: "var(--text-muted, #999)", margin: "2px 0 6px" }, children: "Estado al que se mover\u00E1 el ticket cuando el agente termine." }), trackerStates.length > 0 ? (_jsxs("select", { className: styles.input, value: wf.transition_state, onChange: (e) => patchWorkflow(filename, "transition_state", e.target.value), children: [_jsx("option", { value: "", children: "\u2014 Sin transici\u00F3n autom\u00E1tica \u2014" }), trackerStates.map((s) => (_jsx("option", { value: s, children: s }, s)))] })) : (_jsx("input", { className: styles.input, type: "text", placeholder: "Ej: In Progress", value: wf.transition_state, onChange: (e) => patchWorkflow(filename, "transition_state", e.target.value) })), _jsxs("label", { className: styles.labelSm, style: { marginTop: 8 }, children: [_jsx("input", { type: "checkbox", style: { marginRight: 6 }, checked: wf.requires_prior_output, onChange: (e) => patchWorkflow(filename, "requires_prior_output", e.target.checked) }), "Requiere output del agente anterior (requires_prior_output)"] }), _jsx("button", { type: "button", className: styles.btnAccent, style: { marginTop: 10, fontSize: 12, padding: "4px 14px" }, disabled: savingWorkflow === filename, onClick: () => saveWorkflow(filename), children: savingWorkflow === filename ? "Guardando…" : "💾 Guardar workflow" })] })] }, filename));
                                })] }))] }), _jsxs("div", { className: styles.footer, children: [_jsx("button", { className: styles.btnDanger, onClick: onDelete, disabled: saving, style: { marginRight: "auto" }, children: "\uD83D\uDDD1 Eliminar" }), _jsx("button", { className: styles.btnGhost, onClick: onClose, disabled: saving, children: "Cancelar" }), _jsx("button", { className: styles.btnAccent, onClick: handleSubmit, disabled: saving, children: saving ? "Guardando…" : "Guardar cambios" })] })] }) }));
}
