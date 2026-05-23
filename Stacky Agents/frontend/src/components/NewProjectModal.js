import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from "react";
import { Projects, Mantis } from "../api/endpoints";
import styles from "./NewProjectModal.module.css";
const EMPTY = {
    name: "",
    display_name: "",
    workspace_root: "",
    docs_technical_path: "",
    docs_functional_path: "",
    docs_paths: { technical: "", functional: "" },
    tracker_type: "azure_devops",
    organization: "",
    ado_project: "",
    area_path: "",
    pat: "",
    jira_url: "",
    jira_key: "",
    api_version: "3",
    jql: "",
    verify_ssl: true,
    jira_user: "",
    jira_token: "",
    mantis_url: "",
    mantis_project_id: "",
    mantis_project_name: "",
    mantis_protocol: "rest",
    mantis_token: "",
    mantis_username: "",
    mantis_password: "",
};
export default function NewProjectModal({ onClose, onCreated }) {
    const [form, setForm] = useState({ ...EMPTY });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const [docsChecking, setDocsChecking] = useState(false);
    const [docsCheckMessage, setDocsCheckMessage] = useState(null);
    // Mantis: listar proyectos disponibles
    const [mantisProjects, setMantisProjects] = useState([]);
    const [mantisLoading, setMantisLoading] = useState(false);
    const [mantisLoadError, setMantisLoadError] = useState(null);
    function patch(key, value) {
        setForm((f) => ({ ...f, [key]: value }));
        if (key === "docs_technical_path" || key === "docs_functional_path") {
            setDocsCheckMessage(null);
        }
    }
    function buildPayload() {
        const docs_paths = {
            technical: (form.docs_technical_path || "").trim(),
            functional: (form.docs_functional_path || "").trim(),
        };
        return { ...form, docs_paths };
    }
    async function browseDocsPath(kind) {
        setError(null);
        const currentPath = kind === "technical" ? form.docs_technical_path : form.docs_functional_path;
        try {
            const res = await Projects.browseFolder({
                title: kind === "technical" ? "Seleccionar documentación técnica" : "Seleccionar documentación funcional / manual",
                initial_dir: currentPath || form.workspace_root || "",
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
            setDocsCheckMessage("No configuraste rutas de documentación. Stacky usará autodiscovery en workspace_root/docs.");
            return;
        }
        setDocsChecking(true);
        try {
            const res = await Projects.testDocsPaths(form.name.trim() || "_new", payload);
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
    function setTrackerType(type) {
        setForm((f) => ({ ...f, tracker_type: type }));
        // Reset mantis project list when switching away
        if (type !== "mantis") {
            setMantisProjects([]);
            setMantisLoadError(null);
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
        if (protocol === "soap" && !username) {
            setMantisLoadError("Ingresá el usuario de Mantis para SOAP.");
            return;
        }
        if (protocol !== "soap" && !token) {
            setMantisLoadError("Ingresá el token de API de Mantis.");
            return;
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
    async function handleSubmit() {
        setError(null);
        if (!form.name.trim()) {
            setError("Ingresá un nombre de proyecto");
            return;
        }
        if (!form.workspace_root.trim()) {
            setError("Ingresá el workspace root");
            return;
        }
        if (form.tracker_type === "azure_devops") {
            if (!form.organization?.trim()) {
                setError("Ingresá la organización de Azure DevOps");
                return;
            }
            if (!form.ado_project?.trim()) {
                setError("Ingresá el proyecto de Azure DevOps");
                return;
            }
        }
        else if (form.tracker_type === "jira") {
            if (!form.jira_url?.trim()) {
                setError("Ingresá la URL de Jira");
                return;
            }
            if (!form.jira_key?.trim()) {
                setError("Ingresá la clave del proyecto Jira");
                return;
            }
        }
        else {
            if (!form.mantis_url?.trim()) {
                setError("Ingresá la URL de Mantis");
                return;
            }
            if (!form.mantis_project_id?.trim()) {
                setError("Selecci\u00f3n un proyecto de Mantis");
                return;
            }
            const protocol = form.mantis_protocol || "rest";
            if (protocol === "soap") {
                if (!form.mantis_username?.trim()) {
                    setError("Ingres\u00e1 el usuario de Mantis (SOAP)");
                    return;
                }
            }
            else {
                if (!form.mantis_token?.trim()) {
                    setError("Ingres\u00e1 el token de API de Mantis");
                    return;
                }
            }
        }
        setSaving(true);
        try {
            const result = await Projects.init(buildPayload());
            if (result.ok) {
                onCreated(result.project.name, result.project.display_name);
                onClose();
            }
            else {
                setError(result.error || "Error desconocido");
            }
        }
        catch (e) {
            setError(e?.message || "Error de conexión");
        }
        finally {
            setSaving(false);
        }
    }
    const isAdo = form.tracker_type === "azure_devops";
    const isJira = form.tracker_type === "jira";
    const isMantis = form.tracker_type === "mantis";
    return (_jsx("div", { className: styles.backdrop, onClick: (e) => { if (e.target === e.currentTarget)
            onClose(); }, children: _jsxs("div", { className: styles.panel, children: [_jsx("h2", { className: styles.title, children: "\uD83D\uDCC1 Inicializar Nuevo Proyecto" }), _jsxs("div", { className: styles.body, children: [_jsx("label", { className: styles.label, children: "Nombre interno del proyecto (ID, en may\u00FAsculas)" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: RSPACIFICO, B2IMPACT", value: form.name, onChange: (e) => patch("name", e.target.value.toUpperCase()) }), _jsx("label", { className: styles.label, children: "Nombre para mostrar" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: RS Pac\u00EDfico", value: form.display_name ?? "", onChange: (e) => patch("display_name", e.target.value) }), _jsx("label", { className: styles.label, children: "Workspace root (ruta al c\u00F3digo fuente)" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: C:\\Repos\\MiProyecto\\trunk", value: form.workspace_root, onChange: (e) => patch("workspace_root", e.target.value) }), _jsxs("div", { className: styles.docsPathSection, children: [_jsx("span", { className: styles.trackerHeading, children: "Documentaci\u00F3n del proyecto (opcional)" }), _jsxs("p", { className: styles.note, children: ["Si dej\u00E1s ambas vac\u00EDas, Stacky mantiene el autodiscovery actual de carpetas ", _jsx("code", { children: "docs/" }), "."] }), _jsx("label", { className: styles.label, children: "Documentaci\u00F3n t\u00E9cnica" }), _jsxs("div", { className: styles.pathRow, children: [_jsx("input", { className: styles.input, type: "text", placeholder: "Ej: C:\\Docs\\MiProyecto\\tecnica", value: form.docs_technical_path ?? "", onChange: (e) => patch("docs_technical_path", e.target.value) }), _jsx("button", { type: "button", className: styles.btnPath, onClick: () => browseDocsPath("technical"), children: "Examinar..." })] }), _jsx("label", { className: styles.label, children: "Documentaci\u00F3n funcional / manual" }), _jsxs("div", { className: styles.pathRow, children: [_jsx("input", { className: styles.input, type: "text", placeholder: "Ej: C:\\Docs\\MiProyecto\\funcional", value: form.docs_functional_path ?? "", onChange: (e) => patch("docs_functional_path", e.target.value) }), _jsx("button", { type: "button", className: styles.btnPath, onClick: () => browseDocsPath("functional"), children: "Examinar..." })] }), _jsxs("div", { className: styles.docsActions, children: [_jsx("button", { type: "button", className: styles.btnLoadProjects, onClick: testDocsPaths, disabled: docsChecking, children: docsChecking ? "Validando..." : "Probar rutas docs" }), docsCheckMessage && _jsx("span", { className: styles.docsCheckOk, children: docsCheckMessage })] })] }), _jsx("hr", { className: styles.divider }), _jsx("label", { className: styles.label, children: "Sistema de tickets" }), _jsxs("div", { className: styles.trackerRow, children: [_jsx("button", { type: "button", className: `${styles.trackerBtn} ${isAdo ? styles.trackerBtnActive : ""}`, onClick: () => setTrackerType("azure_devops"), children: "\uD83D\uDD37 Azure DevOps" }), _jsx("button", { type: "button", className: `${styles.trackerBtn} ${isJira ? styles.trackerBtnJira : ""}`, onClick: () => setTrackerType("jira"), children: "\uD83D\uDD35 Jira" }), _jsx("button", { type: "button", className: `${styles.trackerBtn} ${isMantis ? styles.trackerBtnMantis : ""}`, onClick: () => setTrackerType("mantis"), children: "\uD83D\uDFE2 Mantis BT" })] }), isAdo && (_jsxs("div", { className: styles.trackerFields, children: [_jsx("span", { className: styles.trackerHeading, children: "\uD83D\uDD37 Azure DevOps" }), _jsx("label", { className: styles.label, children: "Organizaci\u00F3n ADO" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: UbimiaPacifico", value: form.organization ?? "", onChange: (e) => patch("organization", e.target.value) }), _jsx("label", { className: styles.label, children: "Proyecto ADO" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: Strategist_Pacifico", value: form.ado_project ?? "", onChange: (e) => patch("ado_project", e.target.value) }), _jsx("label", { className: styles.label, children: "Personal Access Token (PAT)" }), _jsx("input", { className: styles.input, type: "password", placeholder: "Peg\u00E1 tu PAT de Azure DevOps", value: form.pat ?? "", onChange: (e) => patch("pat", e.target.value) }), _jsxs("details", { className: styles.advanced, children: [_jsx("summary", { children: "\uD83D\uDD0D Opciones avanzadas ADO" }), _jsxs("div", { className: styles.advancedBody, children: [_jsx("label", { className: styles.labelSm, children: "Area Path (opcional)" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: Strategist_Pacifico\\AgendaWeb", value: form.area_path ?? "", onChange: (e) => patch("area_path", e.target.value) })] })] })] })), isJira && (_jsxs("div", { className: styles.trackerFields, children: [_jsx("span", { className: `${styles.trackerHeading} ${styles.trackerHeadingJira}`, children: "\uD83D\uDD35 Jira" }), _jsx("label", { className: styles.label, children: "URL de la instancia Jira" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: https://empresa.atlassian.net  o  https://jira.intranet.com", value: form.jira_url ?? "", onChange: (e) => patch("jira_url", e.target.value) }), _jsx("label", { className: styles.label, children: "Clave del proyecto (project key)" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: B2IM, PROJ, DEV", value: form.jira_key ?? "", onChange: (e) => patch("jira_key", e.target.value) }), _jsx("label", { className: styles.label, children: "Usuario / Email" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: me@empresa.com", value: form.jira_user ?? "", onChange: (e) => patch("jira_user", e.target.value) }), _jsx("label", { className: styles.label, children: "API Token" }), _jsx("input", { className: styles.input, type: "password", placeholder: "Peg\u00E1 tu API token de Jira", value: form.jira_token ?? "", onChange: (e) => patch("jira_token", e.target.value) }), _jsxs("details", { className: styles.advanced, children: [_jsx("summary", { className: styles.advancedJira, children: "\uD83D\uDD0D Opciones avanzadas Jira" }), _jsxs("div", { className: styles.advancedBody, children: [_jsx("label", { className: styles.labelSm, children: "Versi\u00F3n API" }), _jsxs("select", { className: styles.select, value: form.api_version ?? "3", onChange: (e) => patch("api_version", e.target.value), children: [_jsx("option", { value: "3", children: "v3 \u2014 Jira Cloud (*.atlassian.net)" }), _jsx("option", { value: "2", children: "v2 \u2014 Jira Server / Data Center" })] }), _jsx("label", { className: styles.labelSm, children: "JQL personalizado (opcional)" }), _jsx("textarea", { className: styles.textarea, placeholder: "Ej: assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC", value: form.jql ?? "", onChange: (e) => patch("jql", e.target.value) }), _jsxs("label", { className: styles.checkboxRow, children: [_jsx("input", { type: "checkbox", checked: form.verify_ssl === false, onChange: (e) => patch("verify_ssl", !e.target.checked) }), "Desactivar verificaci\u00F3n SSL (redes corporativas con CA custom)"] })] })] }), _jsxs("p", { className: styles.note, children: ["Las credenciales se guardan cifradas en ", _jsxs("code", { children: ["backend/projects/", "{nombre}", "/auth/jira_auth.json"] }), "."] })] })), isMantis && (_jsxs("div", { className: styles.trackerFields, children: [_jsx("span", { className: `${styles.trackerHeading} ${styles.trackerHeadingMantis}`, children: "\uD83D\uDFE2 Mantis Bug Tracker" }), _jsx("label", { className: styles.label, children: "Protocolo de conexi\u00F3n" }), _jsxs("div", { className: styles.trackerRow, children: [_jsx("button", { type: "button", className: `${styles.trackerBtn} ${form.mantis_protocol !== "soap" ? styles.trackerBtnActive : ""}`, onClick: () => { patch("mantis_protocol", "rest"); setMantisProjects([]); setMantisLoadError(null); }, children: "\uD83D\uDD11 REST (Token API)" }), _jsx("button", { type: "button", className: `${styles.trackerBtn} ${form.mantis_protocol === "soap" ? styles.trackerBtnActive : ""}`, onClick: () => { patch("mantis_protocol", "soap"); setMantisProjects([]); setMantisLoadError(null); }, children: "\uD83D\uDD0C SOAP (Usuario/Contrase\u00F1a)" })] }), _jsx("label", { className: styles.label, children: "URL de la instancia Mantis" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Ej: https://mantis.empresa.com", value: form.mantis_url ?? "", onChange: (e) => patch("mantis_url", e.target.value) }), form.mantis_protocol === "soap" ? (_jsxs(_Fragment, { children: [_jsx("label", { className: styles.label, children: "Usuario de Mantis" }), _jsx("input", { className: styles.input, type: "text", placeholder: "Usuario de Mantis (ej: admin)", value: form.mantis_username ?? "", onChange: (e) => patch("mantis_username", e.target.value) }), _jsx("label", { className: styles.label, children: "Contrase\u00F1a" }), _jsx("input", { className: styles.input, type: "password", placeholder: "Contrase\u00F1a de Mantis", value: form.mantis_password ?? "", onChange: (e) => patch("mantis_password", e.target.value) })] })) : (_jsxs(_Fragment, { children: [_jsx("label", { className: styles.label, children: "API Token" }), _jsx("input", { className: styles.input, type: "password", placeholder: "Token de API de Mantis (Mi Cuenta \u2192 Tokens API)", value: form.mantis_token ?? "", onChange: (e) => patch("mantis_token", e.target.value) })] })), _jsx("button", { type: "button", className: styles.btnLoadProjects, onClick: loadMantisProjects, disabled: mantisLoading, children: mantisLoading ? "Cargando proyectos…" : "🔄 Cargar proyectos de Mantis" }), mantisLoadError && (_jsx("div", { className: styles.errorSmall, children: mantisLoadError })), mantisProjects.length > 0 && (_jsxs(_Fragment, { children: [_jsx("label", { className: styles.label, children: "Proyecto Mantis" }), _jsxs("select", { className: styles.select, value: form.mantis_project_id ?? "", onChange: (e) => {
                                                const selected = mantisProjects.find((p) => p.id === e.target.value);
                                                patch("mantis_project_id", e.target.value);
                                                patch("mantis_project_name", selected?.name ?? "");
                                            }, children: [_jsx("option", { value: "", children: "\u2014 Seleccion\u00E1 un proyecto \u2014" }), mantisProjects.map((p) => (_jsxs("option", { value: p.id, children: ["#", p.id, " \u2014 ", p.name, p.description ? ` (${p.description.slice(0, 40)})` : ""] }, p.id)))] }), form.mantis_project_id && (_jsxs("p", { className: styles.note, children: ["Proyecto seleccionado: ", _jsx("strong", { children: form.mantis_project_name || form.mantis_project_id })] }))] })), !mantisProjects.length && !mantisLoadError && (_jsx("p", { className: styles.note, children: form.mantis_protocol === "soap"
                                        ? "Ingresá la URL, usuario y contraseña, luego hacé clic en \"Cargar proyectos\"."
                                        : "Ingresá la URL y el token, luego hacé clic en \"Cargar proyectos\"." })), _jsxs("details", { className: styles.advanced, children: [_jsx("summary", { children: "\uD83D\uDD0D Opciones avanzadas Mantis" }), _jsx("div", { className: styles.advancedBody, children: _jsxs("label", { className: styles.checkboxRow, children: [_jsx("input", { type: "checkbox", checked: form.verify_ssl === false, onChange: (e) => patch("verify_ssl", !e.target.checked) }), "Desactivar verificaci\u00F3n SSL (redes corporativas con CA custom)"] }) })] }), _jsxs("p", { className: styles.note, children: ["Las credenciales se guardan cifradas en ", _jsxs("code", { children: ["backend/projects/", "{nombre}", "/auth/mantis_auth.json"] }), "."] })] })), _jsxs("p", { className: styles.hint, children: ["Se crear\u00E1 ", _jsxs("code", { children: ["backend/projects/", "{nombre}", "/config.json"] }), " con la configuraci\u00F3n del proyecto."] }), error && _jsx("div", { className: styles.error, children: error })] }), _jsxs("div", { className: styles.footer, children: [_jsx("button", { className: styles.btnGhost, onClick: onClose, disabled: saving, children: "Cancelar" }), _jsx("button", { className: styles.btnAccent, onClick: handleSubmit, disabled: saving, children: saving ? "Inicializando…" : "Crear e inicializar" })] })] }) }));
}
