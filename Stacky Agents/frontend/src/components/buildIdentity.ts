// Plan 163 F2 — helpers PUROS de identidad de build (sin JSX, sin efectos).
// El chip del TopBar y el banner de drift consumen estas funciones; los tests
// las ejercitan sin render (no hay RTL/jsdom en el frontend).

export interface BuildIdentity {
  version: string | null;
  sourceCommit: string | null;
  builtAt: string | null;
  drift: boolean;
}

/** Etiqueta del chip: "v1.0.76 · a1b2c3d" (o "dev@local" si no hay version). */
export function versionChipLabel(b: BuildIdentity): string {
  const v = b.version ? `v${b.version}` : "dev@local";
  const h = b.sourceCommit ? ` · ${shortHash(b.sourceCommit)}` : "";
  return `${v}${h}`;
}

/** Short-hash defensivo (el backend ya manda short, pero por si llega largo). */
export function shortHash(commit: string | null | undefined): string {
  return commit ? commit.slice(0, 7) : "";
}

/** Tooltip del chip: incluye built_at legible. */
export function buildTooltip(b: BuildIdentity): string {
  const parts: string[] = [];
  parts.push(b.version ? `Versión ${b.version}` : "dev@local");
  if (b.sourceCommit) parts.push(`commit ${shortHash(b.sourceCommit)}`);
  if (b.builtAt) parts.push(`build ${b.builtAt}`);
  return parts.join(" · ");
}

/** Texto del banner de drift (sólo se muestra si drift === true). */
export function driftMessage(b: BuildIdentity): string {
  return `El servidor está corriendo código anterior al del repo (commit ${shortHash(b.sourceCommit)}). ` +
         `Reiniciá el backend para tomar los últimos cambios.`;
}
