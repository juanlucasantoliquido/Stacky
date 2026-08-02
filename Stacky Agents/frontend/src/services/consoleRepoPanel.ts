/**
 * Plan 265 F4 (frontend) — Agrupado y presentación de archivos del panel de
 * Repositorio. Lógica pura, sin React.
 */

export interface RepoFile {
  path: string;
  status: string;
}

export interface GroupedRepoFiles {
  conflictos: RepoFile[];
  modified: RepoFile[];
  new: RepoFile[];
  deleted: RepoFile[];
  renombrados: RepoFile[];
  untracked: RepoFile[];
  otros: RepoFile[];
}

/**
 * Los siete pares de `git status` que significan CONFLICTO (dos versiones
 * enfrentadas del mismo archivo). Se comparan por par COMPLETO, nunca con
 * `includes`.
 *
 * Plan 293 F5 — antes de este plan, el orden de evaluación era `includes("A")`
 * y después `includes("D")`, así que `AA` (agregado por los dos lados) salía
 * como "nuevo" y `DD` (borrado por los dos lados) como "borrado": dos de los
 * tres conflictos se mostraban como si todo estuviera bien. `UU` caía en
 * "otros". El pliego pide identificar los archivos en conflicto, y eso exige
 * mirarlos PRIMERO.
 */
const PARES_EN_CONFLICTO = new Set(["DD", "AU", "UD", "UA", "DU", "AA", "UU"]);

/** Agrupa los archivos de `git status --porcelain=v1`. Los conflictos van
 *  PRIMERO. Un status desconocido cae en "otros", nunca se pierde. Nunca lanza. */
export function groupFilesByStatus(files: RepoFile[]): GroupedRepoFiles {
  const result: GroupedRepoFiles = {
    conflictos: [], modified: [], new: [], deleted: [],
    renombrados: [], untracked: [], otros: [],
  };
  if (!Array.isArray(files)) return result;
  for (const f of files) {
    const code = (f?.status || "").trim();
    if (code === "??") {
      result.untracked.push(f);
    } else if (PARES_EN_CONFLICTO.has(code)) {
      result.conflictos.push(f);
    } else if (code.includes("R")) {
      result.renombrados.push(f);
    } else if (code.includes("A")) {
      result.new.push(f);
    } else if (code.includes("D")) {
      result.deleted.push(f);
    } else if (code.includes("M")) {
      result.modified.push(f);
    } else {
      result.otros.push(f);
    }
  }
  return result;
}

/** Elide el medio de una ruta larga para que quepa en `max` caracteres. */
export function shortPath(path: string, max: number): string {
  if (typeof path !== "string") return "";
  if (path.length <= max) return path;
  if (max <= 3) return path.slice(0, Math.max(max, 0));
  const keepEnd = Math.floor((max - 3) / 2);
  const keepStart = max - 3 - keepEnd;
  return `${path.slice(0, keepStart)}...${path.slice(path.length - keepEnd)}`;
}
