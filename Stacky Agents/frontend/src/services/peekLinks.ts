// Plan 175 F1 — Los links que copia y abre el menú contextual.
//
// Delega en el builder canónico de rutas (`serializeRoute`) en vez de armar la
// URL a mano: un deep-link escrito a dedo se desincroniza del día que cambie el
// contrato de rutas, y el operador pega un link que no lleva a ningún lado.

import { adoUrl } from "../utils/trackerUrls";
import { serializeRoute } from "./routes";

export function executionDeepLink(id: number, origin: string): string {
  // `query` es obligatorio en RouteState: omitirlo no compila.
  return `${origin}${serializeRoute({ tab: "history", exec: id, query: {} })}`;
}

/** El link externo del ticket, o null si no hay a dónde ir. */
export function ticketExternalLink(t: { ado_url?: string; ado_id: number }): string | null {
  // La URL que vino del tracker manda sobre la que sabemos construir: si el
  // proyecto cambió de organización, la construida apuntaría al lugar viejo.
  if (t.ado_url) return t.ado_url;
  if (t.ado_id > 0) return adoUrl(String(t.ado_id));
  return null;
}
