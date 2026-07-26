import { useEffect, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Executions } from "../api/endpoints";
import {
  createPrefetchScheduler,
  PREFETCH_DETAIL_STALE_TIME_MS,
} from "../services/prefetchPolicy";
import { useUiPerfFlags } from "./useUiPerfFlags";

/**
 * Plan 174 F3 — Precargar el detalle mientras el operador decide si abrirlo.
 *
 * El gesto más frecuente del cockpit (apuntar una fila y abrirla) pasa de
 * "spinner siempre" a instantáneo, gastando a lo sumo el GET que el click iba a
 * gastar igual.
 *
 * Con la flag apagada devuelve `{}`: ni un handler de más colgado de la fila.
 */
export function usePrefetchExecutionDetail() {
  const qc = useQueryClient();
  const { prefetch } = useUiPerfFlags();

  const scheduler = useMemo(
    () =>
      createPrefetchScheduler((key) =>
        qc.prefetchQuery({
          queryKey: ["execution-detail", Number(key)],
          queryFn: () => Executions.byId(Number(key)),
          staleTime: PREFETCH_DETAIL_STALE_TIME_MS,
        }),
      ),
    [qc],
  );

  // Al desmontar, los timers pendientes se cancelan: un unmount no puede dejar
  // requests fantasma en camino.
  useEffect(() => () => scheduler.dispose(), [scheduler]);

  function getPrefetchProps(id: number) {
    if (!prefetch) return {};
    const key = String(id);
    return {
      onMouseEnter: () => scheduler.enter(key),
      onMouseLeave: () => scheduler.leave(key),
      onFocus: () => scheduler.enter(key),
      onBlur: () => scheduler.leave(key),
    };
  }

  return { getPrefetchProps };
}

export default usePrefetchExecutionDetail;
