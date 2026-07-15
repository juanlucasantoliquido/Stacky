import { useQuery } from "@tanstack/react-query";
import {
  ACTIVE_RUNS_QUERY_KEY,
  ACTIVE_RUNS_REFRESH_MS,
  fetchActiveRuns,
} from "../services/activeRuns";

/**
 * Runs activos (running/preparing/queued) de TODOS los proyectos, refresco 5 s.
 * Todos los consumidores comparten queryKey ⇒ react-query hace UNA request.
 */
export function useActiveRunsGlobal() {
  return useQuery({
    queryKey: ACTIVE_RUNS_QUERY_KEY,
    queryFn: fetchActiveRuns,
    refetchInterval: ACTIVE_RUNS_REFRESH_MS,
    // C1 (v2): sin esto react-query PAUSA el interval con la pestaña oculta
    // (default refetchIntervalInBackground=false; main.tsx:8-10 no lo overridea)
    // y el notificador (F2), el título (F3) y el TopBar (F4) se congelan justo
    // cuando el operador aparta la vista. SOLO esta query paga el costo de
    // seguir viva en background (§3.2).
    refetchIntervalInBackground: true,
  });
}
