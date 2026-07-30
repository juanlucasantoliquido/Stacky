/**
 * Plan 265 F5(c) — Búsqueda en la conversación, puramente cliente sobre las
 * líneas ya en memoria. Lógica pura, sin React.
 */
import type { LogLine } from "../types";

export interface SearchHit {
  lineIndex: number;
  start: number;
  end: number;
}

function escapeRegExp(literal: string): string {
  return literal.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Busca `query` en las líneas. Case-insensitive. `query` vacío -> []. Nunca
 *  lanza. `query` se trata como TEXTO LITERAL, no como expresión de búsqueda
 *  avanzada (una entrada inválida del operador no puede romper la consola, y
 *  un comodín no puede colgarla). */
export function searchLines(lines: LogLine[], query: string): SearchHit[] {
  if (!Array.isArray(lines) || typeof query !== "string" || query.length === 0) return [];
  const pattern = new RegExp(escapeRegExp(query), "gi");
  const hits: SearchHit[] = [];
  for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
    const message = typeof lines[lineIndex]?.message === "string" ? lines[lineIndex].message : "";
    pattern.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(message)) !== null) {
      hits.push({ lineIndex, start: match.index, end: match.index + match[0].length });
      if (match[0].length === 0) pattern.lastIndex += 1; // evita loop infinito en match vacío
    }
  }
  return hits;
}

/** Índice del hit siguiente, con vuelta al principio. Lista vacía -> null. */
export function nextHit(hits: SearchHit[], current: number | null): number | null {
  if (!Array.isArray(hits) || hits.length === 0) return null;
  if (current === null || current === undefined) return 0;
  return (current + 1) % hits.length;
}

/** Índice del hit anterior, con vuelta al final. Lista vacía -> null. */
export function prevHit(hits: SearchHit[], current: number | null): number | null {
  if (!Array.isArray(hits) || hits.length === 0) return null;
  if (current === null || current === undefined) return hits.length - 1;
  return (current - 1 + hits.length) % hits.length;
}
