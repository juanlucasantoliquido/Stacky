import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * AgentConfigModal -- configuracion de roles por agente.
 *
 * Permite marcar tres flags por agente:
 *   - Stacky     -> disponible como empleado en el equipo
 *   - Utilitario -> disponible en el chat drawer de Stacky
 *   - VS Code    -> cuando utilitario+vscode, el chat se abre en VS Code;
 *                  solo vscode -> agente solo accesible desde VS Code
 *
 * Portado de WS2 (Sprint 3). Requiere AgentRoles en api/endpoints.ts y
 * GET /api/agent-roles en el backend (api/agent_roles.py).
 */
import { useEffect, useState } from "react";
import { AgentRoles } from "../api/endpoints";
import styles from "./AgentConfigModal.module.css";
const FLAG_META = [
    { key: "stacky", label: "Stacky", title: "Disponible como empleado del equipo" },
    { key: "utilitario", label: "Utilitario", title: "Disponible en el chat drawer de Stacky" },
    { key: "vscode", label: "VS Code", title: "Se abre en VS Code (requiere Utilitario para chat, o solo para uso exclusivo en VS Code)" },
];
export default function AgentConfigModal({ onClose }) {
    const [roles, setRoles] = useState({});
    const [loading, setLoading] = useState(true);
    const [fetchError, setFetchError] = useState(false);
    const [saving, setSaving] = useState(false);
    const [dirty, setDirty] = useState({});
    const [saved, setSaved] = useState(false);
    useEffect(() => {
        AgentRoles.list()
            .then((res) => setRoles(res.roles ?? {}))
            .catch(() => {
            setRoles({});
            setFetchError(true);
        })
            .finally(() => setLoading(false));
    }, []);
    function toggle(filename, key) {
        setRoles((prev) => {
            const current = prev[filename];
            if (!current)
                return prev;
            const updated = { ...current, [key]: !current[key] };
            return { ...prev, [filename]: updated };
        });
        setDirty((prev) => {
            const current = roles[filename];
            if (!current)
                return prev;
            return {
                ...prev,
                [filename]: {
                    ...(prev[filename] ?? {}),
                    [key]: !current[key],
                },
            };
        });
        setSaved(false);
    }
    async function handleSave() {
        if (!Object.keys(dirty).length) {
            onClose();
            return;
        }
        setSaving(true);
        try {
            await AgentRoles.update(dirty);
            setSaved(true);
            setDirty({});
            setTimeout(() => onClose(), 900);
        }
        catch {
            // ignore -- changes still applied locally
        }
        finally {
            setSaving(false);
        }
    }
    const filenames = Object.keys(roles).sort((a, b) => (roles[a].name || a).localeCompare(roles[b].name || b));
    return (_jsx("div", { className: styles.overlay, onClick: (e) => e.target === e.currentTarget && onClose(), children: _jsxs("div", { className: styles.modal, role: "dialog", "aria-modal": "true", "aria-label": "Configuracion de agentes", children: [_jsxs("header", { className: styles.header, children: [_jsx("span", { className: styles.title, children: "Configuracion de agentes" }), _jsx("button", { className: styles.closeBtn, onClick: onClose, title: "Cerrar", children: "X" })] }), _jsx("p", { className: styles.subtitle, children: "Configura el rol de cada agente detectado en VS Code." }), loading ? (_jsx("div", { className: styles.loadingRow, children: "Cargando agentes..." })) : fetchError ? (_jsxs("div", { className: styles.errorRow, children: ["No se pudo conectar con el backend.", _jsx("br", {}), _jsx("small", { children: "Reinicia el backend y vuelve a abrir este modal." })] })) : filenames.length === 0 ? (_jsx("div", { className: styles.loadingRow, children: "No se encontraron agentes en VS Code." })) : (_jsx("div", { className: styles.tableWrapper, children: _jsxs("table", { className: styles.table, children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { className: styles.thName, children: "Agente" }), FLAG_META.map((f) => (_jsx("th", { className: styles.thFlag, title: f.title, children: f.label }, f.key)))] }) }), _jsx("tbody", { children: filenames.map((fn) => {
                                    const entry = roles[fn];
                                    return (_jsxs("tr", { className: styles.row, children: [_jsxs("td", { className: styles.tdName, children: [_jsx("span", { className: styles.agentName, children: entry.name || fn }), entry.description && (_jsx("span", { className: styles.agentDesc, children: entry.description }))] }), FLAG_META.map((f) => (_jsx("td", { className: styles.tdFlag, children: _jsx("label", { className: styles.checkLabel, title: f.title, children: _jsx("input", { type: "checkbox", checked: !!entry[f.key], onChange: () => toggle(fn, f.key), className: styles.checkbox }) }) }, f.key)))] }, fn));
                                }) })] }) })), _jsxs("footer", { className: styles.footer, children: [_jsx("button", { className: styles.cancelBtn, onClick: onClose, disabled: saving, children: "Cancelar" }), _jsx("button", { className: `${styles.saveBtn}${saved ? " " + styles.saveBtnOk : ""}`, onClick: handleSave, disabled: saving || loading, children: saved ? "Guardado" : saving ? "Guardando..." : "Guardar" })] })] }) }));
}
