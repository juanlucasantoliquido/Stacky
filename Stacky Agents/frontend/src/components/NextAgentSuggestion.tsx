/*
 * FA-42 — Suggested next agent.
 * Después de aprobar una exec, sugiere qué agente correr a continuación
 * basado en transiciones históricas (markov). Si no hay datos, usa la
 * cadena clásica del pipeline como fallback.
 */
import { useQuery } from "@tanstack/react-query";

import { Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import type { AgentType } from "../types";
import styles from "./NextAgentSuggestion.module.css";

interface Props {
  afterAgent: AgentType;
}

export default function NextAgentSuggestion({ afterAgent }: Props) {
  const { setActiveAgent } = useWorkbench();
  const { data } = useQuery({
    queryKey: ["next-suggestion", afterAgent],
    queryFn: () => Agents.nextSuggestion(afterAgent),
    staleTime: 60_000,
  });

  if (!data || data.length === 0) return null;

  return (
    <div className={styles.box}>
      <span className={styles.label}>siguientes que se suelen correr:</span>
      {data.map((s) => (
        <button
          key={s.agent_type}
          className={styles.btn}
          onClick={() => setActiveAgent(s.agent_type)}
          title={
            s.source === "history"
              ? `${Math.round(s.probability * 100)}% de los operadores (n=${s.sample_size})`
              : "Sucesor por defecto del pipeline"
          }
        >
          → {s.agent_type}
          <span className={styles.prob}>
            {s.source === "history"
              ? ` ${Math.round(s.probability * 100)}%`
              : " (default)"}
          </span>
        </button>
      ))}
    </div>
  );
}
