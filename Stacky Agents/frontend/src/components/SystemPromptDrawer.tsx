/*
 * FA-50 — Agent forking inline.
 * Permite ver el system prompt default y editarlo SOLO para este Run.
 * No modifica la definición global del agente. Persiste en metadata como
 * system_prompt_source = "override".
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import type { AgentType } from "../types";
import styles from "./SystemPromptDrawer.module.css";

interface Props {
  agentType: AgentType;
}

export default function SystemPromptDrawer({ agentType }: Props) {
  const { systemPromptOverride, setSystemPromptOverride } = useWorkbench();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string>("");

  const { data } = useQuery({
    queryKey: ["agent-system-prompt", agentType],
    queryFn: () => Agents.systemPrompt(agentType),
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (!systemPromptOverride && data) {
      setDraft(data.system_prompt);
    }
  }, [data, systemPromptOverride]);

  const isOverridden = systemPromptOverride != null;

  return (
    <div className={styles.wrapper}>
      <button
        className={styles.toggle}
        onClick={() => setOpen((v) => !v)}
        title="Ver / forkear el system prompt para este Run (no modifica el default)"
      >
        ⚙ {isOverridden ? "system prompt: forked" : "system prompt"}
        {open ? " ▾" : " ▸"}
      </button>

      {open && (
        <div className={styles.panel}>
          <textarea
            className={styles.editor}
            value={isOverridden ? systemPromptOverride : draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setSystemPromptOverride(e.target.value);
            }}
            rows={10}
          />
          <div className={styles.actions}>
            <button
              className={styles.reset}
              onClick={() => {
                setSystemPromptOverride(null);
                if (data) setDraft(data.system_prompt);
              }}
              disabled={!isOverridden}
            >
              Volver al default
            </button>
            <span className={styles.hint}>
              {isOverridden
                ? "Override activo. Solo aplica a este Run."
                : "Editando = forkear. Sólo afecta este Run."}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
