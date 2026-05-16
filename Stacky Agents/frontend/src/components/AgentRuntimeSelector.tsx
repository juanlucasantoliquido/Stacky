import { Github, TerminalSquare } from "lucide-react";
import type { AgentRuntime } from "../types";
import styles from "./AgentRuntimeSelector.module.css";

interface AgentRuntimeSelectorProps {
  value: AgentRuntime;
  onChange: (runtime: AgentRuntime) => void;
  disabled?: boolean;
}

const OPTIONS: { value: AgentRuntime; label: string; title: string; icon: typeof Github }[] = [
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
          return (
            <button
              key={option.value}
              type="button"
              className={active ? styles.optionActive : styles.option}
              onClick={() => onChange(option.value)}
              disabled={disabled}
              title={option.title}
              aria-pressed={active}
            >
              <Icon size={14} strokeWidth={2.2} />
              <span>{option.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
