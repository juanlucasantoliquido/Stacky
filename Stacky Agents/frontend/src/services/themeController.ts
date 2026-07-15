/* Plan 141 F1 — controlador de tema (efectos DOM). La LÓGICA vive en theme.ts (puro). */
import {
  THEME_STORAGE_KEY,
  normalizeChoice,
  resolveTheme,
  type ThemeChoice,
  type EffectiveTheme,
} from "./theme";

const MQ_DARK = "(prefers-color-scheme: dark)";

/** Lee la elección persistida, tolerante a modo privado. */
export function readStoredChoice(): ThemeChoice {
  try {
    return normalizeChoice(localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return "dark";
  }
}

function prefersDark(): boolean {
  try {
    return !!(window.matchMedia && window.matchMedia(MQ_DARK).matches);
  } catch {
    return false;
  }
}

/** Aplica el tema efectivo al <html>. Idempotente. */
export function applyEffectiveTheme(effective: EffectiveTheme): void {
  try {
    document.documentElement.setAttribute("data-theme", effective);
    // [ADICIÓN ARQUITECTO v3] color-scheme nativo síncrono: alinea el fondo, los scrollbars
    // y los controles nativos del UA con el tema SIN esperar a que theme.css aplique
    // --color-scheme. El inline style gana por especificidad; se mantiene en sync acá.
    document.documentElement.style.colorScheme = effective;
  } catch {
    /* sin DOM: no-op */
  }
}

/**
 * Persiste la elección, la aplica al instante y devuelve el tema efectivo.
 * NO re-monta la app: solo cambia el atributo del <html>.
 */
export function setTheme(choice: ThemeChoice): EffectiveTheme {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    /* best-effort */
  }
  const eff = resolveTheme(choice, prefersDark());
  applyEffectiveTheme(eff);
  return eff;
}

/**
 * Idempotente. Aplica el tema actual e instala el listener del SO para que el
 * modo "system" reaccione a cambios de preferencia mientras la app está abierta.
 */
export function initThemeController(): void {
  applyEffectiveTheme(resolveTheme(readStoredChoice(), prefersDark()));
  try {
    const mq = window.matchMedia(MQ_DARK);
    const onChange = () => {
      if (readStoredChoice() === "system") {
        applyEffectiveTheme(resolveTheme("system", mq.matches));
      }
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if ((mq as unknown as { addListener?: (cb: () => void) => void }).addListener) {
      (mq as unknown as { addListener: (cb: () => void) => void }).addListener(onChange); // Safari viejo
    }
  } catch {
    /* sin matchMedia: "system" se resuelve una vez, sin listener */
  }
}
