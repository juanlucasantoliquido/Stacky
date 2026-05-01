import { useMutation } from "@tanstack/react-query";

import { Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";

export function useOpenChat() {
  const { modelOverride, vsCodeAgent } = useWorkbench();

  return useMutation({
    mutationFn: (payload: { ticket_id: number; context_blocks: any[] }) =>
      Agents.openChat({
        ticket_id: payload.ticket_id,
        context_blocks: payload.context_blocks,
        vscode_agent_filename: vsCodeAgent?.filename ?? undefined,
        model_override: modelOverride,
      }),
  });
}
