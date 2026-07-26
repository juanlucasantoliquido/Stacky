import { useEffect } from "react";

import { isEditableTarget, isUiShortcutsEnabled, shortcutRegistry } from "../services/shortcuts";

/**
 * Plan 172 F2 — El ÚNICO listener de teclado global de la app. Se monta una vez.
 *
 * Antes cada pantalla ponía su propio `addEventListener("keydown")`: nadie podía
 * saber qué teclas estaban tomadas, y dos pantallas peleando por la misma tecla
 * se descubría usándola.
 */
export function useGlobalShortcutListener(): void {
  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      const t = ev.target as HTMLElement | null;
      const handled = shortcutRegistry.dispatch(
        {
          key: ev.key,
          ctrlKey: ev.ctrlKey,
          metaKey: ev.metaKey,
          shiftKey: ev.shiftKey,
          altKey: ev.altKey,
        },
        {
          editable: isEditableTarget(t?.tagName ?? "", t?.isContentEditable),
          dialogOpen: document.querySelector('[role="dialog"]') != null,
          enabled: isUiShortcutsEnabled(),
        },
      );
      // Solo se cancela el evento si un atajo lo tomó: si no, se rompería el
      // tipeo normal en toda la app.
      if (handled) ev.preventDefault();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}

export default useGlobalShortcutListener;
