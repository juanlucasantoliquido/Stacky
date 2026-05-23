import { UiSections } from "../api/endpoints";
import {
  OPTIONAL_SECTIONS,
  LOCKED_SECTIONS,
  isLockedSection,
  isOptionalSection,
  useUiSectionsStore,
  type OptionalSection,
  type SectionKey,
} from "../store/uiSectionsStore";

export { OPTIONAL_SECTIONS, LOCKED_SECTIONS };
export type { OptionalSection, SectionKey };

/**
 * Hidrata el store con el estado de visibilidad del backend.
 * Llamar una sola vez al arrancar la app. Si el backend no responde, se
 * mantienen los defaults (todas visibles).
 */
export async function initUiSections(): Promise<void> {
  try {
    const res = await UiSections.list();
    const next: Partial<Record<OptionalSection, boolean>> = {};
    for (const key of OPTIONAL_SECTIONS) {
      const entry = res.sections?.[key];
      if (entry && typeof entry.visible === "boolean") {
        next[key] = entry.visible;
      }
    }
    useUiSectionsStore.getState().setAll(next);
  } catch {
    // Backend offline — defaults ya están en el store.
  }
}

/** True para `team`/`tickets`/`settings` y para opcionales en `visible: true`. */
export function isSectionVisible(key: SectionKey): boolean {
  if (isLockedSection(key)) return true;
  if (!isOptionalSection(key)) return true;
  return useUiSectionsStore.getState().sections[key];
}

/**
 * Persiste el cambio en backend y actualiza el store en caso de éxito.
 * Lanza si el backend responde error (para que la UI pueda mostrar toast).
 */
export async function setSectionVisible(
  key: OptionalSection,
  visible: boolean,
): Promise<void> {
  const previous = useUiSectionsStore.getState().sections[key];
  // Optimistic update.
  useUiSectionsStore.getState().setSection(key, visible);
  try {
    const res = await UiSections.set(key, visible);
    const next: Partial<Record<OptionalSection, boolean>> = {};
    for (const k of OPTIONAL_SECTIONS) {
      const entry = res.sections?.[k];
      if (entry && typeof entry.visible === "boolean") {
        next[k] = entry.visible;
      }
    }
    useUiSectionsStore.getState().setAll(next);
  } catch (err) {
    // Rollback si falla.
    useUiSectionsStore.getState().setSection(key, previous);
    throw err;
  }
}
