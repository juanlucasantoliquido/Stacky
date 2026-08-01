// Plan 175 F1 — Los links que copia y abre el menú contextual.
//
// Delega en el builder canónico de rutas (`serializeRoute`) en vez de armar la
// URL a mano: un deep-link escrito a dedo se desincroniza del día que cambie el
// contrato de rutas, y el operador pega un link que no lleva a ningún lado.

import { urlDeTicket } from "../utils/trackerUrls";
import { serializeRoute } from "./routes";

export function executionDeepLink(id: number, origin: string): string {
  // `query` es obligatorio en RouteState: omitirlo no compila.
  return `${origin}${serializeRoute({ tab: "history", exec: id, query: {} })}`;
}

/** El link externo del ticket, o null si no hay a dónde ir. */
export function ticketExternalLink(
  t: { ado_url?: string; ado_id: number; tracker_type?: string },
): string | null {
  // La URL que vino del tracker manda sobre la que sabemos construir: si el
  // proyecto cambió de organización, la construida apuntaría al lugar viejo.
  // Plan 282 F5 — sin la URL del backend, sólo se construye si hay organización
  // y proyecto REALES. Antes se devolvía una URL a la organización de OTRO
  // cliente, incluso en proyectos GitLab.
  if (t.ado_url) return t.ado_url;
  if (t.ado_id > 0) return urlDeTicket({ type: t.tracker_type, ado_url: t.ado_url }, t.ado_id);
  return null;
}
