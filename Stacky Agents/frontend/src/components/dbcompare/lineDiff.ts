// Plan 176 F8 — Diff por líneas para definiciones de vistas.
//
// Hoy el drill-down muestra dos <pre> lado a lado y el operador tiene que
// encontrar a ojo qué cambió en una vista de 200 líneas. Esto marca las líneas.
//
// Es un LCS clásico, sin dependencias: el guardrail de la serie prohíbe sumar
// librerías por algo de este tamaño.

export type LineOp = "equal" | "added" | "removed";

export interface DiffLine {
  op: LineOp;
  text: string;
  /** Número de línea en origen (1-based). null si la línea no existe ahí. */
  sourceNo: number | null;
  /** Número de línea en destino (1-based). null si la línea no existe ahí. */
  targetNo: number | null;
}

/** Cap duro: una definición gigante no puede colgar la UI con un LCS O(n·m). */
const MAX_LINES = 2000;

function splitLines(text: string | null | undefined): string[] {
  if (!text) return [];
  return String(text).replace(/\r\n/g, "\n").split("\n");
}

/**
 * Tabla LCS. Con entradas por encima del cap se cae a "todo cambió", que es
 * honesto: preferimos un diff burdo a colgar el navegador.
 */
function lcsTable(a: string[], b: string[]): number[][] {
  const tabla: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array(b.length + 1).fill(0)
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      tabla[i][j] =
        a[i] === b[j]
          ? tabla[i + 1][j + 1] + 1
          : Math.max(tabla[i + 1][j], tabla[i][j + 1]);
    }
  }
  return tabla;
}

export function diffLines(
  source: string | null | undefined,
  target: string | null | undefined
): DiffLine[] {
  const a = splitLines(source);
  const b = splitLines(target);

  if (!a.length && !b.length) return [];

  if (a.length > MAX_LINES || b.length > MAX_LINES) {
    // Degradación honesta: se marca todo como cambiado en vez de colgar.
    return [
      ...a.map((text, i) => ({
        op: "removed" as LineOp,
        text,
        sourceNo: i + 1,
        targetNo: null,
      })),
      ...b.map((text, i) => ({
        op: "added" as LineOp,
        text,
        sourceNo: null,
        targetNo: i + 1,
      })),
    ];
  }

  const tabla = lcsTable(a, b);
  const salida: DiffLine[] = [];
  let i = 0;
  let j = 0;

  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      salida.push({ op: "equal", text: a[i], sourceNo: i + 1, targetNo: j + 1 });
      i++;
      j++;
    } else if (tabla[i + 1][j] >= tabla[i][j + 1]) {
      salida.push({ op: "removed", text: a[i], sourceNo: i + 1, targetNo: null });
      i++;
    } else {
      salida.push({ op: "added", text: b[j], sourceNo: null, targetNo: j + 1 });
      j++;
    }
  }
  while (i < a.length) {
    salida.push({ op: "removed", text: a[i], sourceNo: i + 1, targetNo: null });
    i++;
  }
  while (j < b.length) {
    salida.push({ op: "added", text: b[j], sourceNo: null, targetNo: j + 1 });
    j++;
  }
  return salida;
}

/** Cuántas líneas cambiaron de verdad. Un "0 cambios" con dos textos distintos
 *  sería mentira, así que se cuenta sobre el resultado del diff. */
export function countChanges(lines: DiffLine[]): { added: number; removed: number } {
  return {
    added: lines.filter((l) => l.op === "added").length,
    removed: lines.filter((l) => l.op === "removed").length,
  };
}

/** Solo los tramos con cambio, con N líneas de contexto. Una vista de 200
 *  líneas con 2 cambios no se lee entera. */
export function collapseUnchanged(lines: DiffLine[], context = 3): DiffLine[] {
  const relevante = new Set<number>();
  lines.forEach((l, i) => {
    if (l.op !== "equal") {
      for (let k = i - context; k <= i + context; k++) {
        if (k >= 0 && k < lines.length) relevante.add(k);
      }
    }
  });
  if (!relevante.size) return [];
  return lines.filter((_, i) => relevante.has(i));
}

export function lineClass(op: LineOp): string {
  if (op === "added") return "lineAdded";
  if (op === "removed") return "lineRemoved";
  return "lineEqual";
}
