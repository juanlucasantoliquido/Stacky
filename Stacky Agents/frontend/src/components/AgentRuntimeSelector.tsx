import { Github, TerminalSquare, Terminal } from "lucide-react";
import type { AgentRuntime } from "../types";
import styles from "./AgentRuntimeSelector.module.css";

interface AgentRuntimeSelectorProps {
  value: AgentRuntime;
  onChange: (runtime: AgentRuntime) => void;
  disabled?: boolean;
  /** Si true, marca Claude Code como pendiente de configurar (badge ⚙). */
  claudeNeedsConfig?: boolean;
}

interface RuntimeOption {
  value: AgentRuntime;
  label: string;
  title: string;
  icon: typeof Github;
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
    title: "Ejecutar el agente con Claude Code CLI y logs en Stacky",
    icon: Terminal,
  },
];

export default function AgentRuntimeSelector({
  value,
  onChange,
  disabled = false,
  claudeNeedsConfig = false,
}: AgentRuntimeSelectorProps) {
  return (
    <div className={styles.root}>
      <span className={styles.label}>Ejecutar con</span>
      <div className={styles.segmented} role="group" aria-label="Runtime del agente">
        {OPTIONS.map((option) => {
          const Icon = option.icon;
          const active = option.value === value;
          const needsConfig = option.value === "claude_code_cli" && claudeNeedsConfig;
          return (
            <button
              key={option.value}
              type="button"
              className={active ? styles.optionActive : styles.option}
              onClick={() => onChange(option.value)}
              disabled={disabled}
              title={needsConfig ? "Claude Code — falta configurar (clic para configurar)" : option.title}
              aria-pressed={active}
            >
              <Icon size={14} strokeWidth={2.2} />
              <span>{option.label}</span>
              {needsConfig && (
                <span className={styles.badge} aria-label="requiere configuración">
                  ⚙ configurar
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
