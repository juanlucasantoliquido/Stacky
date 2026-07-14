/**
 * Plan 129 F4 — helper compartido para que los receptores de deep-links lean
 * un query param UNA vez al montar. `parseQueryParam` es puro (testeable sin
 * jsdom); `readQueryParam` es el wrapper que lee `window.location.search`.
 */
export function parseQueryParam(search: string, name: string): string | null {
  return new URLSearchParams(search).get(name);
}

export function readQueryParam(name: string): string | null {
  return parseQueryParam(window.location.search, name);
}
