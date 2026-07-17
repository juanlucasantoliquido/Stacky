export const MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/**
 * Tiempo relativo en español con corte a fecha absoluta.
 * Reglas de corte (congeladas):
 *   - iso vacío/inválido            -> "—"
 *   - futuro (t > now) o diff < 60s -> "recién"
 *   - diff < 60 min                 -> "hace N min"   (N = floor(seg/60), N>=1)
 *   - diff < 24 h                   -> "hace N h"     (N = floor(seg/3600))
 *   - diff < 7 días                 -> "hace N d"     (N = floor(seg/86400))
 *   - diff >= 7 días                -> "D MES YYYY"   (UTC, ej "3 jul 2026")
 * @param iso   timestamp ISO (o null/undefined)
 * @param nowMs epoch ms de "ahora" (default Date.now()); explícito en tests para determinismo.
 */
export function formatRelativeTime(iso: string | null | undefined, nowMs: number = Date.now()): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";

  const diffSec = Math.floor((nowMs - t) / 1000);
  if (diffSec < 60) return "recién"; // cubre futuro (diffSec negativo) y < 60s

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `hace ${diffMin} min`;

  const diffH = Math.floor(diffSec / 3600);
  if (diffH < 24) return `hace ${diffH} h`;

  const diffD = Math.floor(diffSec / 86400);
  if (diffD < 7) return `hace ${diffD} d`;

  const d = new Date(t);
  return `${d.getUTCDate()} ${MESES_ABREV[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
