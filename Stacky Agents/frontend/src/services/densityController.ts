/* Plan 150 F2 — controlador de densidad (efectos DOM). Lógica pura en density.ts. */
import { normalizeDensity, DENSITY_STORAGE_KEY, type Density } from "./density";

/** Duración del settle. La transición usa --transition-opacity (--duration-fast = 0.12s,
 *  theme.css:130,149); 200ms ≥ 120ms deja margen holgado para remover el atributo
 *  DESPUÉS de que el fundido terminó. (C5: no es --duration-base.) */
const DENSITY_SETTLE_MS = 200;

function readDensity(): Density {
  try {
    return normalizeDensity(localStorage.getItem(DENSITY_STORAGE_KEY));
  } catch {
    return "comodo";
  }
}

function applyDensity(d: Density): void {
  document.documentElement.setAttribute("data-density", d);
}

/** Lee la preferencia y la aplica al <html>. Idempotente; llamar en main.tsx. */
export function initDensity(): void {
  applyDensity(readDensity());
}

/** Cambia densidad: persiste, aplica y dispara el settle de opacity. Sin re-render de React. */
export function setDensity(d: Density): void {
  try {
    localStorage.setItem(DENSITY_STORAGE_KEY, d);
  } catch {
    /* modo privado / storage lleno — se aplica igual en memoria */
  }
  const root = document.documentElement;
  root.setAttribute("data-density-animating", "");
  applyDensity(d);
  window.setTimeout(() => root.removeAttribute("data-density-animating"), DENSITY_SETTLE_MS);
}

/** Lee la densidad actual (para inicializar el estado del toggle). */
export function currentDensity(): Density {
  return readDensity();
}
