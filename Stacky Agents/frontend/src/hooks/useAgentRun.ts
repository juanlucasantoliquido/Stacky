import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Agents } from "../api/endpoints";
import { openConsoleIfCliRuntime } from "../services/agentLaunch";
import { useWorkbench } from "../store/workbench";
import type { AgentType, ContextBlock } from "../types";

export function useAgentRun() {
  const qc = useQueryClient();
  const {
    setRunningExecution,
    setActiveExecution,
    setCodexConsoleExecution,
    modelOverride,
    systemPromptOverride,
    agentRuntime,
    vsCodeAgent,
    activeProject,
  } = useWorkbench();

  return useMutation({
    mutationFn: (payload: {
      agent_type: AgentType;
      ticket_id: number;
      context_blocks: ContextBlock[];
      chain_from?: number[];
    }) =>
      Agents.runWithOptions({
        ...payload,
        project: activeProject?.name ?? undefined,
        model_override: modelOverride,
        system_prompt_override: systemPromptOverride,
        runtime: agentRuntime,
        // codex_cli requiere vscode_agent_filename. Se envía siempre que haya
        // un agente VS Code seleccionado en el workbench; el backend lo requiere
        // cuando runtime=codex_cli y lo ignora en los demás casos.
        vscode_agent_filename: vsCodeAgent?.filename ?? undefined,
      }),
    onSuccess: (data) => {
      setRunningExecution(data.execution_id);
      setActiveExecution(data.execution_id);
      // Para runtimes CLI (codex_cli / claude_code_cli) abrimos la consola
      // in-page con el execution_id recién creado. Centralizar acá cubre a
      // InputContextEditor y a cualquier consumidor futuro del hook, evitando
      // que un punto de lanzamiento lance sin mostrar la consola en vivo.
      openConsoleIfCliRuntime(agentRuntime, data, (id) =>
        setCodexConsoleExecution(id, false)
      );
      qc.invalidateQueries({ queryKey: ["executions"] });
    },
  });
}
