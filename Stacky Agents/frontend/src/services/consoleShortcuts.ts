/**
 * Plan 265 F6 — Atajos de teclado de la consola, sobre el contrato REAL del
 * registro (services/shortcuts.ts). Lógica pura, sin React.
 *
 * Regla de diseño (D3, D9): todo lo que va al registro global lleva Ctrl (para
 * seguir disparando con foco en un input, ver comboAllowedInEditable); todo lo
 * que no lleva Ctrl va a un onKeyDown local del contenedor de la consola.
 * `Escape` y `Enter`/`Shift+Enter` NO están acá — viven en onKeyDown locales.
 */
import type { CoreShortcutSpec } from "./shortcuts";
import type { ConsolePresentation } from "./consolePresentation";

/** Los 3 atajos propios de la consola que SÍ van al registro global — los 3
 *  llevan Ctrl (D3/D9), así que siguen vivos con el foco dentro de un input. */
export const CONSOLE_SHORTCUT_DEFS: CoreShortcutSpec[] = [
  {
    id: "console.toggle-fullscreen",
    combo: "Ctrl+Shift+Enter",
    scope: "global",
    category: "global",
    description: "Alternar la consola entre la barra de abajo y pantalla completa",
    core: false,
    allowInDialog: false,
  },
  {
    id: "console.focus-search",
    combo: "Ctrl+Shift+F",
    scope: "global",
    category: "global",
    description: "Poner el foco en la búsqueda dentro de la conversación de la consola",
    core: false,
    allowInDialog: false,
  },
  {
    id: "console.copy-all",
    combo: "Ctrl+Shift+C",
    scope: "global",
    category: "global",
    description: "Copiar toda la conversación de la consola",
    core: false,
    allowInDialog: false,
  },
];

/** ¿La consola en esta presentación debe atender `Escape` localmente (D3)?
 *  SÓLO en "full": vuelve a "dock". Nunca lanza. */
export function shouldHandleEscape(presentation: ConsolePresentation): boolean {
  return presentation === "full";
}
