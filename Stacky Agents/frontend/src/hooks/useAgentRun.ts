import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import type { AgentType, ContextBlock } from "../types";

export function useAgentRun() {
  const qc = useQueryClient();
  const { setRunningExecution, setActiveExecution, modelOverride, systemPromptOverride } =
    useWorkbench();

  return useMutation({
    mutationFn: (payload: {
      agent_type: AgentType;
      ticket_id: number;
      context_blocks: ContextBlock[];
      chain_from?: number[];
    }) =>
      Agents.runWithOptions({
        ...payload,
        model_override: modelOverride,
        system_prompt_override: systemPromptOverride,
      }),
    onSuccess: (data) => {
      setRunningExecution(data.execution_id);
      setActiveExecution(data.execution_id);
      qc.invalidateQueries({ queryKey: ["executions"] });
    },
  });
}
