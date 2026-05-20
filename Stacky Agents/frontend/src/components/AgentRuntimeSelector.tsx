import { Github, TerminalSquare, Terminal } from "lucide-react";
import type { AgentRuntime } from "../types";
import styles from "./AgentRuntimeSelector.module.css";

interface AgentRuntimeSelectorProps {
  value: AgentRuntime;
  onChange: (runtime: AgentRuntime) => void;
  disabled?: boolean;
}

interface RuntimeOption {
  value: AgentRuntime;
  label: string;
  title: string;
  icon: typeof Github;
  /** Si true, la opción se muestra pero no es seleccionable (pendiente de implementación). */
  notImplemented?: boolean;
}

const OPTIONS: RuntimeOption[] = [
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

export default function AgentRuntimeSelector({
  value,
  onChange,
  disabled = false,
}: AgentRuntimeSelectorProps) {
  return (
    <div className={styles.root}>
      <span className={styles.label}>Ejecutar con</span>
      <div className={styles.segmented} role="group" aria-label="Runtime del agente">
        {OPTIONS.map((option) => {
          const Icon = option.icon;
          const active = option.value === value;
          const isDisabled = disabled || option.notImplemented;
          return (
            <button
              key={option.value}
              type="button"
              className={active ? styles.optionActive : styles.option}
              onClick={() => !option.notImplemented && onChange(option.value)}
              disabled={isDisabled}
              title={option.title}
              aria-pressed={active}
              aria-disabled={option.notImplemented ?? false}
            >
              <Icon size={14} strokeWidth={2.2} />
              <span>{option.label}</span>
              {option.notImplemented && (
                <span className={styles.badge} aria-label="no implementado">
                  pronto
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
