// Plan 190 F3 — helpers PUROS para el checklist de re-credencialización DevOps
// que devuelve el import de configuración. Sin dependencias de React ni de red.

export interface DevopsImportResult {
  devops?: { credentials_pending?: string[]; credentials_never_set?: string[] };
  skipped_sections?: string[];
}

/**
 * Divide el checklist de re-credencialización:
 * - pending: servidores que TENÍAN password en el origen y aún no lo tienen local (prioridad).
 * - neverSet: servidores que nunca tuvieron password (informativo).
 */
export function credentialsChecklist(
  res: DevopsImportResult | undefined,
): { pending: string[]; neverSet: string[] } {
  return {
    pending: res?.devops?.credentials_pending ?? [],
    neverSet: res?.devops?.credentials_never_set ?? [],
  };
}

/**
 * Nota de secciones omitidas (p. ej. import con la flag DevOps OFF o ruta per-proyecto).
 * Devuelve null si no se omitió ninguna.
 */
export function skippedNote(res: DevopsImportResult | undefined): string | null {
  const s = res?.skipped_sections ?? [];
  if (!s.length) return null;
  return `Secciones omitidas: ${s.join(", ")}`;
}
