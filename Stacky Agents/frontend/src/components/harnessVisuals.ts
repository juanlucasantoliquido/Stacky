/**
 * Plan 78 F1 — Identidad visual por categoría del arnés.
 *
 * CATEGORY_VISUALS: slug (HarnessFlagCategory.id) → {color, icon}.
 * Slugs estables (backend FLAG_CATEGORIES). Si llega una categoría sin
 * entrada en el mapa, visualFor() devuelve FALLBACK_VISUAL (nunca rompe).
 *
 * REGLA: cada slug tiene un icono DISTINTO para permitir reconocimiento por icono.
 * Iconos verificados en lucide-react@0.453.
 */

import {
  Terminal,
  Brain,
  CheckCircle2,
  ShieldCheck,
  BookOpen,
  ListChecks,
  Coins,
  Activity,
  Monitor,
  GraduationCap,
  Compass,
  Database,
  FlaskConical,
  GitMerge,
  Link,
  HelpCircle,
  type LucideIcon,
} from "lucide-react";

export interface CategoryVisual {
  color: string;
  icon: LucideIcon;
}

// slug → identidad visual. Slugs estables = backend FLAG_CATEGORIES ids.
// [C3 fix] observabilidad_notif usa Monitor (no Activity, que ya usa fiabilidad_ciclo_vida).
export const CATEGORY_VISUALS: Record<string, CategoryVisual> = {
  runtimes_cli:          { color: "#6366f1", icon: Terminal },
  contexto_memoria:      { color: "#0ea5e9", icon: Brain },
  calidad_verificacion:  { color: "#22c55e", icon: CheckCircle2 },
  integridad_grounding:  { color: "#14b8a6", icon: ShieldCheck },
  epicas_ado:            { color: "#a855f7", icon: BookOpen },
  flujo_funcional:       { color: "#8b5cf6", icon: ListChecks },
  routing_costo:         { color: "#f59e0b", icon: Coins },
  fiabilidad_ciclo_vida: { color: "#ef4444", icon: Activity },
  observabilidad_notif:  { color: "#3b82f6", icon: Monitor },   // [C3 fix: era Activity, duplicado]
  aprendizaje:           { color: "#ec4899", icon: GraduationCap },
  preflight_intencion:   { color: "#06b6d4", icon: Compass },
  base_datos:            { color: "#64748b", icon: Database },
  avanzado:              { color: "#71717a", icon: FlaskConical },
  migrador_ado_gitlab:   { color: "#fb923c", icon: GitMerge },
  gitlab_deep_links:     { color: "#f97316", icon: Link },
  otros:                 { color: "#9ca3af", icon: HelpCircle },
};

// Fallback determinista: categoría sin entrada → gris + icono genérico. NUNCA rompe.
export const FALLBACK_VISUAL: CategoryVisual = { color: "#9ca3af", icon: HelpCircle };

export function visualFor(catId: string): CategoryVisual {
  return CATEGORY_VISUALS[catId] ?? FALLBACK_VISUAL;
}

/**
 * [ADICIÓN ARQUITECTO — C2] Función PURA que particiona secciones por tier.
 * Encapsula el predicado de F4 para que sea importable y testeable de forma aislada.
 *
 * INVARIANTE garantizado: simpleSections ∪ restSections === allSections (sin solape, sin pérdida).
 * Un filtro por === "simple" y su complemento !== "simple" lo garantiza por construcción.
 * tier=undefined (deploy viejo / mock sin tier) cae en restSections → degradación segura.
 *
 * @param allSections Lista completa de secciones (orderedSections de HarnessFlagsPanel).
 * @returns { simpleSections, restSections } — partición exhaustiva y disjunta.
 */
export function partitionSectionsByTier<T extends { cat: { tier?: string } }>(
  allSections: T[],
): { simpleSections: T[]; restSections: T[] } {
  const simpleSections = allSections.filter((s) => s.cat.tier === "simple");
  const restSections = allSections.filter((s) => s.cat.tier !== "simple");
  return { simpleSections, restSections };
}
