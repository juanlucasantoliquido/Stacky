/**
 * Plan 136 F2 — Borrador del brief de EpicFromBriefModal en sessionStorage.
 * Storage inyectable para tests puros. NUNCA lanza: cualquier fallo de storage
 * (cuota llena, storage deshabilitado) degrada a no-op — jamás rompe el tipeo.
 * sessionStorage muere con la pestaña: el draft no persiste entre sesiones.
 */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const PREFIX = "stacky.epicBriefDraft.v1:";

export function briefDraftKey(project: string | null): string {
  return `${PREFIX}${project ?? "_global"}`;
}

export function readBriefDraft(storage: StorageLike | null, project: string | null): string {
  if (!storage) return "";
  try {
    return storage.getItem(briefDraftKey(project)) ?? "";
  } catch {
    return "";
  }
}

export function writeBriefDraft(
  storage: StorageLike | null,
  project: string | null,
  brief: string,
): void {
  if (!storage) return;
  try {
    if (brief.trim().length === 0) storage.removeItem(briefDraftKey(project));
    else storage.setItem(briefDraftKey(project), brief);
  } catch {
    /* no-op: nunca romper el tipeo por un fallo de storage */
  }
}

export function clearBriefDraft(storage: StorageLike | null, project: string | null): void {
  if (!storage) return;
  try {
    storage.removeItem(briefDraftKey(project));
  } catch {
    /* no-op */
  }
}
