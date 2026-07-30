/**
 * Plan 265 F4 (frontend) — Agrupado y presentación de archivos del panel de
 * Repositorio. Lógica pura, sin React.
 */

export interface RepoFile {
  path: string;
  status: string;
}

export interface GroupedRepoFiles {
  modified: RepoFile[];
  new: RepoFile[];
  deleted: RepoFile[];
  untracked: RepoFile[];
  otros: RepoFile[];
}

/** Agrupa los archivos de `git status --porcelain=v1` en modificados / nuevos /
 *  borrados / sin seguimiento / otros. Un status desconocido cae en "otros",
 *  nunca se pierde. Nunca lanza. */
export function groupFilesByStatus(files: RepoFile[]): GroupedRepoFiles {
  const result: GroupedRepoFiles = { modified: [], new: [], deleted: [], untracked: [], otros: [] };
  if (!Array.isArray(files)) return result;
  for (const f of files) {
    const code = (f?.status || "").trim();
    if (code === "??") {
      result.untracked.push(f);
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
