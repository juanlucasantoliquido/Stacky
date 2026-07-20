import { create } from "zustand";

// "team" (Mi Equipo) es opcional y ocultable; su default es OCULTA (ver
// `defaults` abajo) porque la vista índice de la app es Tickets.
export const OPTIONAL_SECTIONS = ["team", "pm", "logs", "docs", "memory"] as const;
export const LOCKED_SECTIONS = ["tickets", "settings"] as const;

export type OptionalSection = typeof OPTIONAL_SECTIONS[number];
export type LockedSection = typeof LOCKED_SECTIONS[number];
export type SectionKey = OptionalSection | LockedSection;

type VisibilityMap = Record<OptionalSection, boolean>;

interface UiSectionsState {
  sections: VisibilityMap;
  setSection: (key: OptionalSection, visible: boolean) => void;
  setAll: (next: Partial<VisibilityMap>) => void;
}

const defaults: VisibilityMap = {
  team: false, // Mi Equipo arranca oculta — la vista índice es Tickets.
  pm: true,
  logs: true,
  docs: true,
  memory: true,
};

export const useUiSectionsStore = create<UiSectionsState>((set) => ({
  sections: { ...defaults },
  setSection: (key, visible) =>
    set((s) => ({ sections: { ...s.sections, [key]: visible } })),
  setAll: (next) =>
    set((s) => ({ sections: { ...s.sections, ...next } })),
}));

export function isLockedSection(key: string): key is LockedSection {
  return (LOCKED_SECTIONS as readonly string[]).includes(key);
}

export function isOptionalSection(key: string): key is OptionalSection {
  return (OPTIONAL_SECTIONS as readonly string[]).includes(key);
}
