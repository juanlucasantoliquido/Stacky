import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import FlowConfigPage from "./FlowConfigPage";
import { LOCKED_SECTIONS, OPTIONAL_SECTIONS, setSectionVisible, } from "../services/uiSections";
import { useUiSectionsStore } from "../store/uiSectionsStore";
import styles from "./SettingsPage.module.css";
const OPTIONAL_LABELS = {
    pm: { title: "📊 PM", hint: "Tablero de Project Management y métricas de sprint." },
    logs: { title: "🔍 System Logs", hint: "Vista cruda de logs estructurados del backend." },
    docs: { title: "📄 Docs", hint: "Navegador de documentación indexada del proyecto." },
};
const LOCKED_LABELS = {
    team: { title: "⚡ Mi Equipo", hint: "Pantalla principal de operación." },
    tickets: { title: "📋 Tickets ADO", hint: "Tablero de tickets sincronizados con Azure DevOps." },
    settings: { title: "⚙️ Configuración", hint: "Esta misma pantalla — no puede ocultarse." },
};
function SectionsVisibilityPanel() {
    const sections = useUiSectionsStore((s) => s.sections);
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(null);
    const toggle = async (key, next) => {
        setError(null);
        setBusy(key);
        try {
            await setSectionVisible(key, next);
        }
        catch (err) {
            setError(err instanceof Error ? err.message : "No se pudo guardar el cambio.");
        }
        finally {
            setBusy(null);
        }
    };
    return (_jsxs("div", { className: styles.sectionsPanel, children: [_jsxs("p", { className: styles.sectionsIntro, children: ["Eleg\u00ED qu\u00E9 pesta\u00F1as de la barra superior quer\u00E9s ver. Las marcadas como", " ", _jsx("span", { className: styles.lockedBadge, children: "Obligatoria" }), " no se pueden ocultar."] }), OPTIONAL_SECTIONS.map((key) => {
                const meta = OPTIONAL_LABELS[key];
                const checked = sections[key];
                const disabled = busy === key;
                return (_jsxs("div", { className: styles.row, children: [_jsxs("div", { className: styles.rowLabel, children: [_jsx("span", { className: styles.rowTitle, children: meta.title }), _jsx("span", { className: styles.rowHint, children: meta.hint })] }), _jsxs("label", { className: styles.toggle, children: [_jsx("input", { type: "checkbox", checked: checked, disabled: disabled, onChange: (e) => toggle(key, e.target.checked) }), _jsx("span", { className: styles.toggleSlider })] })] }, key));
            }), LOCKED_SECTIONS.map((key) => {
                const meta = LOCKED_LABELS[key];
                return (_jsxs("div", { className: styles.row, children: [_jsxs("div", { className: styles.rowLabel, children: [_jsx("span", { className: styles.rowTitle, children: meta.title }), _jsx("span", { className: styles.rowHint, children: meta.hint })] }), _jsx("span", { className: styles.lockedBadge, children: "Obligatoria" })] }, key));
            }), error && _jsx("div", { className: styles.errorText, children: error })] }));
}
export default function SettingsPage() {
    const [sub, setSub] = useState("flow");
    return (_jsxs("div", { className: styles.root, children: [_jsxs("div", { className: styles.subTabs, children: [_jsx("button", { className: `${styles.subTab} ${sub === "flow" ? styles.active : ""}`, onClick: () => setSub("flow"), children: "Flujo" }), _jsx("button", { className: `${styles.subTab} ${sub === "sections" ? styles.active : ""}`, onClick: () => setSub("sections"), children: "Vista / Secciones" })] }), _jsxs("div", { className: styles.content, children: [sub === "flow" && _jsx(FlowConfigPage, {}), sub === "sections" && _jsx(SectionsVisibilityPanel, {})] })] }));
}
