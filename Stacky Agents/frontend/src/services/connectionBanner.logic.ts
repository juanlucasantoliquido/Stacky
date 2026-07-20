/**
 * connectionBanner.logic.ts — Plan 192 F3 (serie UX). Lógica PURA del banner de
 * conexión (sin React). Los strings son EXACTOS: los tests los fijan.
 */
import type { ConnectionSnapshot } from "./connectionMonitor";

const MSG_DOWN = "Sin conexión con el backend — reintentando…";
const MSG_RECOVERING = "Backend de vuelta — actualizando…";

export interface BannerView {
  visible: boolean;
  kind: "down" | "recovering" | null;
  message: string; // string exacto
  attemptText: string | null; // "(intento N)" o null
  showRetry: boolean;
}

const HIDDEN: BannerView = {
  visible: false,
  kind: null,
  message: "",
  attemptText: null,
  showRetry: false,
};

export function computeBannerView(s: ConnectionSnapshot): BannerView {
  if (!s.enabled) return HIDDEN; // defensa en profundidad
  if (s.status === "down") {
    return {
      visible: true,
      kind: "down",
      message: MSG_DOWN,
      attemptText: s.attempt > 0 ? `(intento ${s.attempt})` : null,
      showRetry: true,
    };
  }
  if (s.status === "recovering") {
    return {
      visible: true,
      kind: "recovering",
      message: MSG_RECOVERING,
      attemptText: null,
      showRetry: false,
    };
  }
  // healthy / suspect: sin banner (suspect evita el falso positivo)
  return HIDDEN;
}

/**
 * "Última respuesta del backend hace Xs" (o "Sin respuesta del backend aún" si
 * lastOkAt es null — string EXACTO fijado por los tests; C7). Redondeo a segundos.
 */
export function freshnessLabel(lastOkAt: number | null, now: number): string {
  if (lastOkAt === null) return "Sin respuesta del backend aún";
  const secs = Math.round((now - lastOkAt) / 1000);
  return `Última respuesta del backend hace ${secs}s`;
}
