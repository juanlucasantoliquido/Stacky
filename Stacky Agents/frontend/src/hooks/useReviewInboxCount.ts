import { useQuery } from "@tanstack/react-query";
import { useWorkbench } from "../store/workbench";
import { fetchReviewInbox, reviewInboxQueryKey } from "../services/reviewInbox";

/** Conteo de runs en needs_review/error (proyecto activo, 30 días) para el badge. */
export function useReviewInboxCount(): number {
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const q = useQuery({
    queryKey: reviewInboxQueryKey(activeProjectName),
    queryFn: () => fetchReviewInbox(activeProjectName),
    refetchInterval: 60_000,
    // C4 (v2): en el arranque activeProject aún es null; sin este guard la query
    // dispara con project omitido y el backend cae al proyecto default
    // (api/executions.py:56) → badge transitorio potencialmente equivocado.
    // (La página conserva su comportamiento actual; el guard es SOLO del badge.)
    enabled: activeProjectName != null,
  });
  return q.data?.length ?? 0;
}
