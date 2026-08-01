/**
 * trackerUrls.ts — Helpers de construcción de URLs de tracker (Plan 75 F4 → 282 F5).
 *
 * Plan 282 F5 — ESTO NO ERA COSMÉTICA. La versión previa devolvía SIEMPRE
 * `https://dev.azure.com/<org>/<proyecto>/_workitems/edit/<id>` con la
 * organización y el proyecto HARDCODEADOS: en un proyecto GitLab, "Abrir en el
 * tracker" y "Copiar link" mandaban al operador a la organización de OTRO
 * cliente. Era un link roto que además filtraba el nombre de un tercero.
 *
 * Regla de resolución, en este orden:
 *   1. Si el item trae su URL del backend (`ado_url` / `item_url`), se usa TAL
 *      CUAL — el backend ya compone las URLs GitLab vía gitlab_deep_links.py.
 *   2. Si el tracker es ADO y hay `organization` + `project` REALES en la config
 *      del proyecto, se construye con ESOS valores.
 *   3. Si no, `null`. El consumidor OCULTA la acción; nunca renderiza un link
 *      muerto ni uno que apunte al tracker de otro cliente.
 */

export interface TrackerUrlContext {
  /** tracker_type del proyecto/ticket ("azure_devops" | "gitlab" | …). */
  type?: string | null;
  /** URL que ya vino del backend. Gana sobre cualquier composición local. */
  ado_url?: string | null;
  /** Organización ADO REAL del proyecto (Project.organization). */
  organization?: string | null;
  /** Proyecto ADO REAL (Project.ado_project). */
  project?: string | null;
}

import { urlsRuteadasActivas } from "../services/trackerUiFlags";

export function urlDeTicket(
  tracker: TrackerUrlContext,
  id: string | number | null | undefined,
): string | null {
  const delBackend = (tracker.ado_url ?? "").trim();
  if (delBackend) return delBackend;

  // Plan 282 F8 — kill-switch STACKY_TRACKER_URLS_ROUTED_ENABLED: con OFF la
  // app NO compone ninguna URL del lado del cliente y usa solo la del backend.
  if (!urlsRuteadasActivas()) return null;

  const tipo = (tracker.type ?? "").trim().toLowerCase();
  // Sólo ADO se puede componer del lado del cliente; GitLab/Jira/Mantis dependen
  // de la instancia del operador y su URL la arma el backend.
  if (tipo && tipo !== "azure_devops") return null;

  const org = (tracker.organization ?? "").trim();
  const proyecto = (tracker.project ?? "").trim();
  if (!org || !proyecto || id == null || id === "") return null;

  return `https://dev.azure.com/${encodeURIComponent(org)}/${encodeURIComponent(proyecto)}/_workitems/edit/${id}`;
}

/**
 * @deprecated Plan 282 F5 — usar `urlDeTicket`, que recibe la organización real
 * del proyecto. Se conserva exportada para no romper importadores de las ramas
 * paralelas; devuelve `null` cuando no hay org/proyecto configurados, en vez de
 * inventar la organización de otro cliente.
 */
export function adoUrl(adoId: string): string | null {
  return urlDeTicket({ type: "azure_devops" }, adoId);
}
