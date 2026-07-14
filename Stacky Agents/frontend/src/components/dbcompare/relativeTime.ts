// Plan 124 — Comparador de BD: tiempo relativo en español para el historial de corridas (doc §F6).

/** Reglas exactas: <60s "hace segundos"; <60m "hace N min"; <24h "hace N h"; si no "hace N d". */
export function relativeTimeEs(iso: string, nowIso: string): string {
  const then = new Date(iso).getTime();
  const now = new Date(nowIso).getTime();
  const diffSec = Math.max(0, Math.floor((now - then) / 1000));

  if (diffSec < 60) return "hace segundos";

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `hace ${diffMin} min`;

  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `hace ${diffH} h`;

  const diffD = Math.floor(diffH / 24);
  return `hace ${diffD} d`;
}
