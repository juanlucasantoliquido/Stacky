/**
 * C20 — Toggle global de "Modo Demo" para mostrar Stacky externamente sin
 * riesgo de filtrar data real ni consumir tokens.
 *
 * El estado vive en localStorage para que persista entre recargas. El componente
 * <DemoModeBanner /> lo lee, y `api.ts` puede inspeccionarlo para redirigir
 * llamadas a fixtures cuando esté activo (los handlers `/api/demo/*`
 * del backend devuelven outputs cacheados).
 */
const KEY = "stacky.demoMode";
const listeners = new Set();
export function isDemoMode() {
    return localStorage.getItem(KEY) === "true";
}
export function setDemoMode(enabled) {
    localStorage.setItem(KEY, enabled ? "true" : "false");
    document.documentElement.dataset.demoMode = enabled ? "true" : "false";
    for (const fn of listeners)
        fn(enabled);
}
export function subscribeDemoMode(fn) {
    listeners.add(fn);
    return () => {
        listeners.delete(fn);
    };
}
// Init on import: hidrata el atributo del root para el CSS global.
if (typeof document !== "undefined") {
    document.documentElement.dataset.demoMode = isDemoMode() ? "true" : "false";
}
