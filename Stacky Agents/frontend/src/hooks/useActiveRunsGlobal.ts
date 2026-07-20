import { useQuery } from "@tanstack/react-query";
import type { AgentExecution, ExecutionsSummary } from "../types";
import {
  executionsSummaryQueryKey,
  fetchExecutionsSummary,
  selectActiveRuns,
  summaryRefetchInterval,
} from "../services/executionsSummary";

/**
 * Runs activos (running/preparing/queued) de TODOS los proyectos.
 *
 * Plan 156 F2 — latido unico: se suscribe a la queryKey central del summary
 * (scope all_projects). react-query deduplica N suscriptores del MISMO scope a
 * UNA request de red por tick. La cache guarda el ExecutionsSummary crudo (para
 * que el notificador global del 152 pueda leer el MISMO canal); `select`
 * proyecta a la lista mergeada que consumen ActiveRunsPanel/TopBar/notifier.
 */
export function useActiveRunsGlobal() {
  return useQuery<ExecutionsSummary, Error, AgentExecution[]>({
    queryKey: executionsSummaryQueryKey("all_projects"),
    queryFn: () => fetchExecutionsSummary("all_projects"),
    select: selectActiveRuns,
    // refetchInterval PURO: x4 con pestaña oculta, x2 si no hay runs activos.
    // query.state.data es el ExecutionsSummary crudo (select no lo altera).
    refetchInterval: (query) =>
      summaryRefetchInterval(document.visibilityState, query.state.data),
    // C1 (v2): sin esto react-query PAUSA el interval con la pestaña oculta
    // (default refetchIntervalInBackground=false; main.tsx:8-10 no lo overridea)
    // y el notificador, el titulo y el TopBar se congelan justo cuando el
    // operador aparta la vista. SOLO esta query paga el costo de background.
    refetchIntervalInBackground: true,
  });
}
