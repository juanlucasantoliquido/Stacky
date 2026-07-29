import { useQuery } from "@tanstack/react-query";
import { Health } from "../api/endpoints";

export interface Plan259Flags {
  onboardingGitlab: boolean;
  setupGuide: boolean;
  setupGuideVerify: boolean;
}

/** Fail-open: si /api/diag/health no responde, TODO se muestra.
 *  El servidor igual valida (F2), así que mostrar de más nunca corrompe datos. */
export const PLAN259_FLAGS_FALLBACK: Plan259Flags = {
  onboardingGitlab: true,
  setupGuide: true,
  setupGuideVerify: true,
};

/**
 * Plan 259 F5.0 — Lee las 3 flags del alta GitLab SIN agregar una request.
 *
 * Calcado del precedente `useUiPerfFlags`: react-query deduplica por key y el
 * staleTime infinito evita refetches, así que este hook lee de la cache
 * compartida en vez de sumar un GET por pantalla.
 */
export function usePlan259Flags(): Plan259Flags {
  const { data } = useQuery({
    queryKey: ["plan259-flags"],
    queryFn: () => Health.get(),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const f = data?.flags;
  if (!f) return PLAN259_FLAGS_FALLBACK;
  // `!== false` y no `=== true`: una clave ausente (servidor viejo) se comporta
  // como encendida.
  return {
    onboardingGitlab: f.STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED !== false,
    setupGuide: f.STACKY_SETUP_GUIDE_ENABLED !== false,
    setupGuideVerify: f.STACKY_SETUP_GUIDE_VERIFY_ENABLED !== false,
  };
}

export default usePlan259Flags;
