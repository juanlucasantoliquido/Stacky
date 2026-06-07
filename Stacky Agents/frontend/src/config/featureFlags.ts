// Feature flags de frontend para la memoria colaborativa.
//
// Plan v2 §11/§12: el MVP shippeable es Fase A (lista de Memorias + Borradores).
// Las vistas de Fase B-F (Triage de hallazgos, Grafo de conflictos, botón
// Validar, badges por ticket) quedan detrás de este flag, OFF por default, hasta
// que el backend de validación/sync esté habilitado y haya demanda real.
//
// Para activarlas en una build: definir VITE_MEMORY_ADVANCED=true en el entorno
// de Vite (p. ej. en `frontend/.env.local`) y reconstruir el frontend.
export const MEMORY_ADVANCED_ENABLED: boolean =
  String(import.meta.env.VITE_MEMORY_ADVANCED ?? "").toLowerCase() === "true";
