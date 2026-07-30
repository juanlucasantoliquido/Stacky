// Plan 263 F6 — helpers PUROS del panel de normalización de estado (HITL).
// .ts a propósito (no .tsx): la UI no se testea sin RTL/jsdom (no instalados
// en este repo), pero esta lógica sí, sin DOM.
import type { NormalizeItem, NormalizePropuestaDto } from "../api/endpoints";

/** Plan 263 v3/ADICIÓN 4 — vocabulario cerrado de estados elegibles a mano. */
export const ESTADOS_ELEGIBLES = ["PROPUESTO", "CRITICADO", "IMPLEMENTADO", "IMPLEMENTADO-PARCIAL"] as const;

/** Nada preseleccionado por default: el operador marca a mano cada fila. */
export function seleccionablesPorDefecto(_propuestas: NormalizePropuestaDto[]): string[] {
  return [];
}

export function resumenConfianza(
  propuestas: NormalizePropuestaDto[]
): { alta: number; media: number; sin_evidencia: number } {
  const out = { alta: 0, media: 0, sin_evidencia: 0 };
  for (const p of propuestas) {
    out[p.confianza] += 1;
  }
  return out;
}

export function puedeAplicar(flagOn: boolean, seleccionados: string[]): boolean {
  return flagOn && seleccionados.length > 0;
}

export function textoConfirmacion(seleccionados: string[]): string {
  return `Se van a modificar ${seleccionados.length} archivos.`;
}

/** Plan 263 v3/ADICIÓN 4 — una fila sin evidencia sólo es seleccionable si el
 * operador ya eligió una etapa del vocabulario cerrado. Nunca se preselecciona. */
export function esSeleccionable(
  propuesta: NormalizePropuestaDto,
  elegidoDelOperador?: string | null
): boolean {
  if (propuesta.aplicable) return true;
  return !!elegidoDelOperador && (ESTADOS_ELEGIBLES as readonly string[]).includes(elegidoDelOperador);
}

/** Arma los items que viajan a PlansBoard.normalizeApply(). Nunca pierde el
 * `sha256_visto`, nunca manda claves de más, y nunca incluye una fila que el
 * servidor rechazaría (sin evidencia y sin estado elegido). */
export function itemsParaApply(
  propuestas: NormalizePropuestaDto[],
  seleccionados: string[],
  elegidos: Record<string, string>
): NormalizeItem[] {
  const seleccionadosSet = new Set(seleccionados);
  const out: NormalizeItem[] = [];
  for (const p of propuestas) {
    if (!seleccionadosSet.has(p.filename)) continue;
    if (!p.sha256_visto) continue;
    const elegido = elegidos[p.filename] ?? null;
    if (!esSeleccionable(p, elegido)) continue;
    if (p.aplicable) {
      out.push({ filename: p.filename, sha256_visto: p.sha256_visto });
    } else {
      out.push({ filename: p.filename, sha256_visto: p.sha256_visto, estado_elegido: elegido });
    }
  }
  return out;
}
