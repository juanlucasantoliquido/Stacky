import { useEffect, useState } from "react";
import { ModelCatalogApi, type ModelCatalogResponse, type RuntimeModelCatalog } from "../api/endpoints";
import { resolveModelCatalog } from "../services/modelCatalogFallback";

/** Plan 159 — hook delgado (useState + useEffect, sin librería nueva) que sirve
 * el catálogo unificado de modelos/efforts a los selectores del frontend.
 *
 * Caché de promesa module-level (C3/C11 frontend): el primer montaje dispara un
 * único fetch; los siguientes reusan la MISMA promesa (un solo request por
 * sesión de página; la frescura viva la maneja el TTL del backend). Nunca deja
 * el selector vacío: aplica resolveModelCatalog al resultado y al error. */
let catalogPromise: Promise<ModelCatalogResponse> | null = null;

function getCatalogPromise(): Promise<ModelCatalogResponse> {
  if (catalogPromise === null) {
    catalogPromise = ModelCatalogApi.get();
  }
  return catalogPromise;
}

export interface UseModelCatalogResult {
  catalog: Record<string, RuntimeModelCatalog>;
  loading: boolean;
}

export function useModelCatalog(): UseModelCatalogResult {
  const [catalog, setCatalog] = useState<Record<string, RuntimeModelCatalog>>(() =>
    resolveModelCatalog(null)
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    getCatalogPromise()
      .then((res) => {
        if (alive) setCatalog(resolveModelCatalog(res));
      })
      .catch(() => {
        if (alive) setCatalog(resolveModelCatalog(null));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return { catalog, loading };
}
