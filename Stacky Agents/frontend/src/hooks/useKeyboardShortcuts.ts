import { useEffect } from "react";

export interface Shortcut {
  combo: string;
  label: string;
  category: "global" | "execution" | "navigation";
  handler?: (ev: KeyboardEvent) => void;
}

function matches(ev: KeyboardEvent, combo: string): boolean {
  const parts = combo.toLowerCase().split("+").map((p) => p.trim());
  const wantCtrl = parts.includes("ctrl") || parts.includes("cmd");
  const wantShift = parts.includes("shift");
  const wantAlt = parts.includes("alt");
  const key = parts[parts.length - 1];

  if (wantCtrl !== (ev.ctrlKey || ev.metaKey)) return false;
  if (wantShift !== ev.shiftKey) return false;
  if (wantAlt !== ev.altKey) return false;
  if (key === "enter") return ev.key === "Enter";
  if (key === "esc" || key === "escape") return ev.key === "Escape";
  if (key === "?") return ev.key === "?" || (ev.shiftKey && ev.key === "/");
  return ev.key.toLowerCase() === key;
}

export function useKeyboardShortcuts(shortcuts: Shortcut[]): void {
  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      const tagName = (ev.target as HTMLElement | null)?.tagName ?? "";
      const isEditable = ["INPUT", "TEXTAREA"].includes(tagName) ||
        (ev.target as HTMLElement | null)?.isContentEditable;

      for (const sc of shortcuts) {
        if (!sc.handler) continue;
        if (isEditable && !sc.combo.toLowerCase().includes("ctrl")) continue;
        if (matches(ev, sc.combo)) {
          ev.preventDefault();
          sc.handler(ev);
          return;
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [shortcuts]);
}

export const DEFAULT_SHORTCUTS: Shortcut[] = [
  { combo: "Ctrl+K", label: "Abrir Command Palette", category: "global" },
  { combo: "?", label: "Mostrar atajos", category: "global" },
  { combo: "Ctrl+R", label: "Re-ejecutar último agente", category: "execution" },
  { combo: "Ctrl+Shift+R", label: "Re-ejecutar cambiando de agente", category: "execution" },
  { combo: "Enter", label: "Correr agente seleccionado", category: "execution" },
  { combo: "Shift+Enter", label: "Correr con edición del prompt", category: "execution" },
  { combo: "Esc", label: "Cerrar modal/drawer", category: "navigation" },
  { combo: "Ctrl+/", label: "Toggle Mi Equipo ↔ Tickets", category: "navigation" },
];
