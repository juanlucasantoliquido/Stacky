import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
import styles from "./AgentWorkflowForm.module.css";
export default function AgentWorkflowForm({ value, onChange, trackerStates, loadingStates = false, loadError = false, projectDisplayName, }) {
    function toggleState(state) {
        const next = value.allowed_states.includes(state)
            ? value.allowed_states.filter((s) => s !== state)
            : [...value.allowed_states, state];
        onChange({ ...value, allowed_states: next });
    }
    function selectAll() {
        onChange({ ...value, allowed_states: [...trackerStates] });
    }
    function clearAll() {
        onChange({ ...value, allowed_states: [] });
    }
    return (_jsxs("div", { className: styles.root, children: [_jsxs("div", { className: styles.section, children: [_jsxs("div", { className: styles.sectionHeader, children: [_jsxs("span", { className: styles.label, children: ["Estados visibles", projectDisplayName && (_jsxs("span", { className: styles.labelMeta, children: [" en ", projectDisplayName] }))] }), trackerStates.length > 0 && (_jsxs("div", { className: styles.bulkActions, children: [_jsx("button", { type: "button", className: styles.bulkBtn, onClick: selectAll, children: "Seleccionar todos" }), _jsx("button", { type: "button", className: styles.bulkBtn, onClick: clearAll, children: "Limpiar" })] }))] }), loadingStates ? (_jsx("p", { className: styles.hint, children: "Cargando estados del tracker\u2026" })) : loadError ? (_jsx("p", { className: styles.hintError, children: "No se pudieron cargar los estados del tracker." })) : trackerStates.length === 0 ? (_jsx("p", { className: styles.hint, children: "Sin estados disponibles. Configur\u00E1 las credenciales del proyecto para cargarlos autom\u00E1ticamente." })) : (_jsx("div", { className: styles.chips, children: trackerStates.map((s) => {
                            const active = value.allowed_states.includes(s);
                            return (_jsxs("button", { type: "button", className: active ? styles.chipActive : styles.chip, onClick: () => toggleState(s), children: [active ? "✓ " : "", s] }, s));
                        }) })), value.allowed_states.length === 0 && trackerStates.length > 0 && (_jsx("p", { className: styles.hintMuted, children: "Sin selecci\u00F3n = ve todos los estados." }))] }), _jsxs("div", { className: styles.section, children: [_jsx("span", { className: styles.label, children: "Estado de transici\u00F3n al terminar" }), !loadingStates && trackerStates.length > 0 ? (_jsxs("select", { className: styles.select, value: value.transition_state, onChange: (e) => onChange({ ...value, transition_state: e.target.value }), children: [_jsx("option", { value: "", children: "\u2014 Sin transici\u00F3n autom\u00E1tica \u2014" }), trackerStates.map((s) => (_jsx("option", { value: s, children: s }, s)))] })) : (_jsx("input", { className: styles.input, type: "text", placeholder: "Ej: In Progress", value: value.transition_state, onChange: (e) => onChange({ ...value, transition_state: e.target.value }) }))] }), _jsx("div", { className: styles.section, children: _jsxs("label", { className: styles.checkboxLabel, children: [_jsx("input", { type: "checkbox", className: styles.checkbox, checked: value.requires_prior_output, onChange: (e) => onChange({ ...value, requires_prior_output: e.target.checked }) }), "Requiere output previo antes de ejecutar este empleado"] }) })] }));
}
