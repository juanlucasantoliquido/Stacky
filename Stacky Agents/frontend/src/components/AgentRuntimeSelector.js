import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Github, TerminalSquare, Terminal } from "lucide-react";
import styles from "./AgentRuntimeSelector.module.css";
const OPTIONS = [
    {
        value: "github_copilot",
        label: "GitHub Copilot",
        title: "Abrir el agente en VS Code Chat",
        icon: Github,
    },
    {
        value: "codex_cli",
        label: "Codex CLI",
        title: "Ejecutar el agente con Codex CLI y logs en Stacky",
        icon: TerminalSquare,
    },
    {
        value: "claude_code_cli",
        label: "Claude Code",
        // Tooltip explícito: el adapter no existe todavía. El botón permanece
        // visible pero deshabilitado para que el operador sepa que la opción
        // está en el roadmap y no la busque en otro lugar.
        title: "Claude Code CLI (no implementado — pendiente AL-01 Fase 1)",
        icon: Terminal,
        notImplemented: true,
    },
];
export default function AgentRuntimeSelector({ value, onChange, disabled = false, }) {
    return (_jsxs("div", { className: styles.root, children: [_jsx("span", { className: styles.label, children: "Ejecutar con" }), _jsx("div", { className: styles.segmented, role: "group", "aria-label": "Runtime del agente", children: OPTIONS.map((option) => {
                    const Icon = option.icon;
                    const active = option.value === value;
                    const isDisabled = disabled || option.notImplemented;
                    return (_jsxs("button", { type: "button", className: active ? styles.optionActive : styles.option, onClick: () => !option.notImplemented && onChange(option.value), disabled: isDisabled, title: option.title, "aria-pressed": active, "aria-disabled": option.notImplemented ?? false, children: [_jsx(Icon, { size: 14, strokeWidth: 2.2 }), _jsx("span", { children: option.label }), option.notImplemented && (_jsx("span", { className: styles.badge, "aria-label": "no implementado", children: "pronto" }))] }, option.value));
                }) })] }));
}
