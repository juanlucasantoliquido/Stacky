/**
 * connectionRecovery.ts — Plan 192 F4 (serie UX). El "momento mágico": al salir
 * de down, UNA invalidación global de react-query re-fetchea SOLO las lecturas
 * activas (default refetchType:'active' de v5); las inactivas quedan stale para su
 * próximo mount. Nunca toca mutaciones. Solo importa tipos de react-query (D7).
 */
import type { QueryClient } from "@tanstack/react-query";

/** Handler de recuperación: UNA invalidación global (refetch de lecturas activas). */
export function makeRecoveryHandler(qc: QueryClient): () => void {
  return () => {
    void qc.invalidateQueries();
  };
}
