import { useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";

import { Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import type { VsCodeAgent } from "../types";
import { colorForAgent } from "./AgentCard";
import card from "./AgentCard.module.css";
import styles from "./AgentSelector.module.css";

export default function AgentSelector() {
  const { vsCodeAgent, setVsCodeAgent, runningExecutionId } = useWorkbench();
  const {
    data: vscode,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["vscode-agents"],
    queryFn: Agents.vsCodeAgents,
    staleTime: 60_000,
  });

  const list = vscode ?? [];
  const isRunning = runningExecutionId != null;

  return (
    <section className={styles.section}>
      <div className={styles.header}>
        <h3 className={styles.title}>
          AGENTES
          {isRunning && (
            <span className={styles.runningPill} title="Agente trabajando…">
              <span className={styles.runningDot} />
              trabajando
            </span>
          )}
        </h3>
        <button
          type="button"
          className={styles.refresh}
          onClick={() => refetch()}
          disabled={isFetching}
          title="Recargar agentes desde la carpeta de prompts de VS Code"
        >
          {isFetching ? "↻" : "⟳"} {isFetching ? "Cargando…" : "Recargar"}
        </button>
      </div>

      {isLoading && <div className={styles.empty}>cargando agentes…</div>}
      {error && (
        <div className={styles.empty}>
          error cargando agentes de VS Code
        </div>
      )}
      {!isLoading && !error && list.length === 0 && (
        <div className={styles.empty}>
          No hay archivos <code>.agent.md</code> en la carpeta de prompts de VS Code.
        </div>
      )}

      <div className={styles.list}>
        {list.map((a) => (
          <VsCodeAgentRow
            key={a.filename}
            agent={a}
            selected={vsCodeAgent?.filename === a.filename}
            running={isRunning && vsCodeAgent?.filename === a.filename}
            onSelect={() => setVsCodeAgent(a)}
          />
        ))}
      </div>
    </section>
  );
}

function VsCodeAgentRow({
  agent,
  selected,
  running,
  onSelect,
}: {
  agent: VsCodeAgent;
  selected: boolean;
  running: boolean;
  onSelect: () => void;
}) {
  const desc =
    agent.description.length > 140
      ? agent.description.slice(0, 140) + "…"
      : agent.description;
  const style = { "--agent-color": colorForAgent("custom") } as CSSProperties;

  return (
    <button
      className={`${card.card} ${selected ? card.selected : ""} ${running ? styles.runningCard : ""}`}
      onClick={onSelect}
      title={agent.description}
      style={style}
      data-agent="custom"
    >
      <div className={card.head}>
        <span className={card.icon}>{running ? <span className={styles.spinnerMini} /> : "✦"}</span>
        <span className={card.name}>{agent.name}</span>
        {running && <span className={styles.workingLabel}>procesando…</span>}
      </div>
      {desc && <div className={card.desc}>{desc}</div>}
    </button>
  );
}
