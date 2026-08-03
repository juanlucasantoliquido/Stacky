import { useCallback, useEffect, useState } from "react";
import { ModelCatalogApi, type ModelCatalogResponse, type RuntimeModelCatalog } from "../api/endpoints";
import { resolveModelCatalog } from "../services/modelCatalogFallback";
import { debeRefrescarCatalogo } from "../services/modelCatalogRefresh";

/** Plan 159 — hook delgado (useState + useEffect, sin librería nueva) que sirve
 * el catálogo unificado de modelos/efforts a los selectores del frontend.
 *
 * Caché de promesa module-level (C3/C11 frontend): el primer montaje dispara un
 * único fetch; los siguientes reusan la MISMA promesa. Nunca deja el selector
 * vacío: aplica resolveModelCatalog al resultado y al error.
 *
 * Plan 288 F9.1 — la promesa de módulo AHORA SE PUEDE INVALIDAR. Sin esto, una
 * pestaña abierta se queda con la primera lista para siempre y el tiempo de vida
 * de 300 s del servidor no sirve de nada del lado del navegador: un modelo nuevo
 * aparecería recién al recargar la aplicación entera. */
let catalogPromise: Promise<ModelCatalogResponse> | null = null;
let catalogPedidoEn = 0;
const TTL_MS = 300_000;

export function invalidarCatalogoModelos(): void {
  catalogPromise = null;
  catalogPedidoEn = 0;
}

function getCatalogPromise(forzar = false): Promise<ModelCatalogResponse> {
  if (catalogPromise === null) {
    catalogPedidoEn = Date.now();
    catalogPromise = ModelCatalogApi.get(forzar);
  }
  return catalogPromise;
}

export interface UseModelCatalogResult {
  catalog: Record<string, RuntimeModelCatalog>;
  loading: boolean;
  /** Plan 288 — la respuesta cruda, para que la pantalla pueda decir de dónde salió. */
  respuesta: ModelCatalogResponse | null;
  /** Plan 288 F9.1 — fuerza una relectura del catálogo. */
  refrescar: () => void;
}

export function useModelCatalog(): UseModelCatalogResult {
  const [catalog, setCatalog] = useState<Record<string, RuntimeModelCatalog>>(() =>
    resolveModelCatalog(null)
  );
  const [loading, setLoading] = useState(true);
  const [respuesta, setRespuesta] = useState<ModelCatalogResponse | null>(null);
  const [tick, setTick] = useState(0);

  const refrescar = useCallback(() => {
    invalidarCatalogoModelos();
    setTick((n) => n + 1);
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getCatalogPromise(tick > 0)
      .then((res) => {
        if (!alive) return;
        setCatalog(resolveModelCatalog(res));
        setRespuesta(res);
      })
      .catch(() => {
        if (!alive) return;
        setCatalog(resolveModelCatalog(null));
        setRespuesta(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [tick]);

  // Plan 288 F9.1 — al volver a la pestaña, si venció el tiempo de vida se
  // vuelve a pedir. NUNCA dispara con la pestaña oculta y NUNCA dos veces
  // seguidas antes del vencimiento: eso es lo que impide que esto sea un sondeo.
  useEffect(() => {
    const alVolver = () => {
      const visible =
        typeof document === "undefined" || document.visibilityState === "visible";
      if (debeRefrescarCatalogo(visible, catalogPedidoEn, Date.now(), TTL_MS)) {
        refrescar();
      }
    };
    window.addEventListener("visibilitychange", alVolver);
    window.addEventListener("focus", alVolver);
    return () => {
      window.removeEventListener("visibilitychange", alVolver);
      window.removeEventListener("focus", alVolver);
    };
  }, [refrescar]);

  return { catalog, loading, respuesta, refrescar };
}
