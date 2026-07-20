import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Agents } from "../api/endpoints";
import { openConsoleIfCliRuntime, parseBusinessPreflightError } from "../services/agentLaunch";
import { useWorkbench } from "../store/workbench";
import { useAlert } from "../components/ui";
import type { AgentType, ContextBlock } from "../types";

export function useAgentRun() {
  const showAlert = useAlert();
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
        // Los runtimes CLI (codex_cli / claude_code_cli) requieren
        // vscode_agent_filename. Se envía siempre que haya un agente VS Code
        // seleccionado en el workbench; el backend lo requiere para esos
        // runtimes y lo ignora en los demás casos.
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
    onError: (err) => {
      // Plan 133 F2 — el preflight de negocio server-side (POST /run) puede
      // rechazar el lanzamiento con un 400 accionable ANTES de gastar el run.
      // Este hook no tenía manejo de error alguno; sin esto, el 400 quedaba
      // mudo para el operador (mono-operador: window.alert es explícito y
      // suficiente, no hay mecanismo de toast en frontend/src/hooks/).
      const message = parseBusinessPreflightError(err);
      if (message) {
        void showAlert({ message });
      }
    },
  });
}
