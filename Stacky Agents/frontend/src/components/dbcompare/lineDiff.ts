// Plan 176 F8 — Diff por líneas para definiciones de vistas.
//
// Hoy el drill-down muestra dos bloques lado a lado y el operador tiene que
// encontrar a ojo qué cambió en una vista de 200 líneas. Esto marca las líneas.
//
// Es un LCS clásico, sin dependencias: el guardrail de la serie prohíbe sumar
// librerías por algo de este tamaño.

export type LineOp = { op: "equal" | "add" | "del"; text: string };

/** Cap duro: una definición gigante no puede colgar la UI con un LCS O(n·m). */
const MAX_LINES = 3000;

/**
 * LCS por programación dinámica sobre líneas. Split por `\n` sin normalizar
 * espacios: dos definiciones que difieren en espacios difieren de verdad.
 *
 * Devuelve `null` por encima del cap. Es a propósito: el caller vuelve al render
 * de dos bloques. Inventar un diff burdo (marcar todo como cambiado) sería peor
 * que no mostrarlo — diría que cambió todo en una vista que quizá no cambió.
 */
export function diffLines(a: string, b: string): LineOp[] | null {
  const izq = String(a ?? "").split("\n");
  const der = String(b ?? "").split("\n");

  if (izq.length > MAX_LINES || der.length > MAX_LINES) return null;

  const n = izq.length;
  const m = der.length;
  const tabla: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      tabla[i][j] =
        izq[i] === der[j] ? tabla[i + 1][j + 1] + 1 : Math.max(tabla[i + 1][j], tabla[i][j + 1]);
    }
  }

  const salida: LineOp[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (izq[i] === der[j]) {
      salida.push({ op: "equal", text: izq[i] });
      i++;
      j++;
    } else if (tabla[i + 1][j] >= tabla[i][j + 1]) {
      salida.push({ op: "del", text: izq[i] });
      i++;
    } else {
      salida.push({ op: "add", text: der[j] });
      j++;
    }
  }
  while (i < n) salida.push({ op: "del", text: izq[i++] });
  while (j < m) salida.push({ op: "add", text: der[j++] });
  return salida;
}

/** Cuántas líneas cambiaron de verdad. Un "sin cambios" con dos textos distintos
 *  sería mentira, así que se cuenta sobre el resultado del diff. */
export function countChanges(lines: LineOp[]): { added: number; removed: number } {
  return {
    added: lines.filter((l) => l.op === "add").length,
    removed: lines.filter((l) => l.op === "del").length,
  };
}

/** Clase CSS por operación. Las líneas iguales no llevan clase. */
export function lineClass(op: LineOp["op"]): string {
  if (op === "add") return "lineAdd";
  if (op === "del") return "lineDel";
  return "";
}
