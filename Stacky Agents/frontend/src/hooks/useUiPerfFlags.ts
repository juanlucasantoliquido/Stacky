import { useQuery } from "@tanstack/react-query";

export interface UiPerfFlags {
  virtualization: boolean;
  prefetch: boolean;
  instantNav: boolean;
}

/** Fail-open: si el health no responde, la UX no se degrada. */
const DEFAULTS: UiPerfFlags = { virtualization: true, prefetch: true, instantNav: true };

/**
 * Plan 174 F1 — Lee las flags de rendimiento SIN agregar una request.
 *
 * react-query deduplica por key y el staleTime infinito evita refetches, así que
 * este hook lee de la cache compartida en vez de sumar un GET por pantalla: el
 * presupuesto de requests por tick del plan 156 queda intacto.
 */
export function useUiPerfFlags(): UiPerfFlags {
  const q = useQuery({
    queryKey: ["ui-perf-flags"],
    queryFn: async (): Promise<UiPerfFlags> => {
      const r = await fetch("/api/diag/health");
      // Chequear r.ok ANTES de .json(): un 500 con cuerpo HTML reventaría el
      // parse y dejaría las flags en un estado indefinido.
      if (!r.ok) return DEFAULTS;
      const d = await r.json();
      return {
        virtualization: d.ui_virtualization_enabled !== false,
        prefetch: d.ui_prefetch_enabled !== false,
        instantNav: d.ui_instant_nav_enabled !== false,
      };
    },
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    retry: 0,
    placeholderData: DEFAULTS,
  });
  return q.data ?? DEFAULTS;
}

export default useUiPerfFlags;
