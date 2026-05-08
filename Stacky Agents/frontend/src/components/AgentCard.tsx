import type { CSSProperties } from "react";

import type { AgentDefinition, AgentType } from "../types";
import styles from "./AgentCard.module.css";

interface Props {
  agent: AgentDefinition;
  selected: boolean;
  onSelect: () => void;
}

const AGENT_COLORS: Record<string, string> = {
  business:   "var(--agent-business)",
  functional: "var(--agent-functional)",
  technical:  "var(--agent-technical)",
  developer:  "var(--agent-developer)",
  qa:         "var(--agent-qa)",
  custom:     "var(--agent-custom)",
};

export function colorForAgent(type: AgentType | string | null | undefined): string {
  if (!type) return "var(--agent-custom)";
  return AGENT_COLORS[type] ?? "var(--agent-custom)";
}

export default function AgentCard({ agent, selected, onSelect }: Props) {
  const style = { "--agent-color": colorForAgent(agent.type) } as CSSProperties;
  return (
    <button
      className={`${styles.card} ${selected ? styles.selected : ""}`}
      onClick={onSelect}
      title={agent.description}
      style={style}
      data-agent={agent.type}
    >
      <div className={styles.head}>
        <span className={styles.icon}>{agent.icon || "•"}</span>
        <span className={styles.name}>{agent.name}</span>
      </div>
      <div className={styles.desc}>{agent.description}</div>
      <div className={styles.meta}>
        <span className="muted">in:</span> {agent.inputs.slice(0, 2).join(", ")}
      </div>
    </button>
  );
}
