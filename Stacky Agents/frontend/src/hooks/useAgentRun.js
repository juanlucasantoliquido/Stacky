import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Agents } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
export function useAgentRun() {
    const qc = useQueryClient();
    const { setRunningExecution, setActiveExecution, modelOverride, systemPromptOverride } = useWorkbench();
    return useMutation({
        mutationFn: (payload) => Agents.runWithOptions({
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
