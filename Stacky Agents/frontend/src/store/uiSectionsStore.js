import { create } from "zustand";
export const OPTIONAL_SECTIONS = ["pm", "logs", "docs"];
export const LOCKED_SECTIONS = ["team", "tickets", "settings"];
const defaults = {
    pm: true,
    logs: true,
    docs: true,
};
export const useUiSectionsStore = create((set) => ({
    sections: { ...defaults },
    setSection: (key, visible) => set((s) => ({ sections: { ...s.sections, [key]: visible } })),
    setAll: (next) => set((s) => ({ sections: { ...s.sections, ...next } })),
}));
export function isLockedSection(key) {
    return LOCKED_SECTIONS.includes(key);
}
export function isOptionalSection(key) {
    return OPTIONAL_SECTIONS.includes(key);
}
