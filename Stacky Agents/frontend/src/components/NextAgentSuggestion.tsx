/*
 * FA-42 — Suggested next agent (Markov / cadena histórica).
 *
 * DEPRECATED — Feature #4 FlowConfig (SDD-2026-05-19).
 * La recomendación del botón "Run Sugerido" en TicketBoard ya NO usa este
 * componente. Fue reemplazada por el mapa determinístico FlowConfig
 * (ado_state → agent_type), cargado una vez en TicketBoard raíz.
 *
 * Este componente SIGUE en uso en OutputPanel.tsx para mostrar sugerencias
 * de cadena post-aprobación (después de que el operador aprueba una ejecución).
 * NO eliminar — preservado para rollback. Ver SDD-2026-05-19 Feature #4.
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
