/**
 * trackerUrls.ts — Helpers de construcción de URLs de tracker (Plan 75 F4).
 *
 * Centraliza la composición de URLs ADO para que los componentes no tengan
 * literales de org/project hardcodeados. El backend construye URLs GitLab
 * (vía gitlab_deep_links.py); las URLs ADO se construyen aquí por backward-
 * compatibility con la linkificación de texto (`linkifyCitations`).
 */

export function adoUrl(adoId: string): string {
  return `https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_workitems/edit/${adoId}`;
}
