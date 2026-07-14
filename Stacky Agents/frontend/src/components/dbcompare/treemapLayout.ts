// Plan 124 — Comparador de BD: layout determinista del treemap (doc §F4, algoritmo "binary
// weight-split" corregido por FIX C4 de la crítica v2: el corte ahora sí minimiza
// |sum(A)-sum(B)| entre los cortes prefijo válidos, comparando el cruce con su vecino anterior).
import type { SchemaDiff, DiffItem } from "./dbcompareTypes";

export interface TreemapInput {
  key: string;
  label: string;
  weight: number;
  state: "added" | "removed" | "changed" | "unchanged";
}

export interface TreemapRect extends TreemapInput {
  x: number;
  y: number;
  w: number;
  h: number;
}

function round2(v: number): number {
  return Math.round(v * 100) / 100;
}

function sumWeights(items: TreemapInput[]): number {
  return items.reduce((s, it) => s + it.weight, 0);
}

/**
 * Índice de corte (1-based, A = items[0:cut]) que minimiza |sum(A)-sum(B)| entre todos los
 * cortes prefijo válidos (A y B siempre no vacíos). O(n): un solo recorrido acumulando, más
 * una comparación con el cruce vecino inmediato anterior.
 */
function splitIndex(items: TreemapInput[]): number {
  const total = sumWeights(items);
  const half = total / 2;
  let acc = 0;
  let cut = 1;
  // i recorre solo hasta items.length-2: así `cut` (= i+1) nunca llega a items.length,
  // lo que garantiza que B = items.slice(cut) sea SIEMPRE no vacío (invariante del algoritmo).
  for (let i = 0; i < items.length - 1; i++) {
    acc += items[i].weight;
    cut = i + 1;
    if (acc >= half) break;
  }
  if (cut > 1) {
    const accPrev = acc - items[cut - 1].weight;
    if (Math.abs(accPrev - half) <= Math.abs(acc - half)) {
      cut = cut - 1;
    }
  }
  return cut;
}

function partition(items: TreemapInput[], x: number, y: number, w: number, h: number, out: TreemapRect[]): void {
  if (items.length === 1) {
    const it = items[0];
    out.push({ ...it, x: round2(x), y: round2(y), w: round2(w), h: round2(h) });
    return;
  }
  const cut = splitIndex(items);
  const A = items.slice(0, cut);
  const B = items.slice(cut);
  const total = sumWeights(items);
  const sumA = sumWeights(A);
  if (w >= h) {
    const wA = (w * sumA) / total;
    partition(A, x, y, wA, h, out);
    partition(B, x + wA, y, w - wA, h, out);
  } else {
    const hA = (h * sumA) / total;
    partition(A, x, y, w, hA, out);
    partition(B, x, y + hA, w, h - hA, out);
  }
}

export function computeTreemapLayout(items: TreemapInput[], width: number, height: number): TreemapRect[] {
  if (items.length === 0) return [];
  const normalized = items
    .map((it) => ({ ...it, weight: Math.max(it.weight, 1) }))
    .sort((a, b) => {
      if (b.weight !== a.weight) return b.weight - a.weight; // DESC
      return a.key < b.key ? -1 : a.key > b.key ? 1 : 0; // empate: key ASC
    });
  const out: TreemapRect[] = [];
  partition(normalized, 0, 0, width, height, out);
  return out;
}

/**
 * Una entrada por TABLA del universo comparado (unión de las tablas mencionadas en el diff y
 * las presentes en `snapshotCounts`): state según el diff (unchanged si no hay item), weight
 * = #columnas tomado de `snapshotCounts["schema.tabla"]` (mapa que arma el caller a partir de
 * los snapshots del run); si la tabla no está en el mapa -> weight=1 (fallback uniforme, no
 * error). label = "schema.tabla". Salida ordenada por key ascendente (determinista).
 */
export function tableTreemapInputs(diff: SchemaDiff, snapshotCounts: Record<string, number>): TreemapInput[] {
  const byKey = new Map<string, DiffItem>();
  for (const item of diff.items) {
    if (item.object_type === "table") {
      byKey.set(`${item.schema}.${item.name}`, item);
    }
  }
  const universe = new Set<string>([...Object.keys(snapshotCounts), ...byKey.keys()]);
  const keys = [...universe].sort();
  return keys.map((key) => {
    const diffItem = byKey.get(key);
    const state: TreemapInput["state"] = diffItem ? diffItem.action : "unchanged";
    const weight = key in snapshotCounts ? snapshotCounts[key] : 1;
    return { key, label: key, weight, state };
  });
}
