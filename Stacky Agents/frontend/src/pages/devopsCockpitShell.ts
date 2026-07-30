/** Plan 239 F4 — helpers puros del shell v3 del cockpit DevOps. Sin DOM, sin React.
 *
 *  F0 aporta solo los TIPOS y la tabla de grupos (los necesita `DevOpsSection.group`);
 *  F4 y F5 agregan las funciones. Todo lo de este archivo es puro y testeable sin jsdom.
 */

import type { DevOpsSection } from './DevOpsPage';

export type DevOpsGroupId = 'resumen' | 'operar' | 'construir' | 'gobernar' | 'diagnosticar';

/** Sección sin `group` ⇒ cae acá. Preserva el contrato §3.12 C20 (KPI-10). */
export const DEFAULT_GROUP: DevOpsGroupId = 'operar';

export interface GroupDef {
  id: DevOpsGroupId;
  label: string;
  hint: string;
}

export const DEVOPS_SECTION_GROUPS: GroupDef[] = [
  { id: 'resumen', label: 'Resumen', hint: 'Estado general y avisos' },
  { id: 'operar', label: 'Operar', hint: 'Desplegar, ambientes, publicaciones y servidores' },
  { id: 'construir', label: 'Construir', hint: 'Pipelines y variables' },
  { id: 'gobernar', label: 'Gobernar', hint: 'Inventario, auditoría, matriz de entornos y paquete de entrega' },
  { id: 'diagnosticar', label: 'Diagnosticar', hint: 'PRs, consola remota y agente DevOps' },
];

/** s.group ?? DEFAULT_GROUP — una sección futura sin `group` sigue funcionando
 *  con 1 sola entrada (contrato §3.12 C20, KPI-10). */
export function groupOf(s: Pick<DevOpsSection, 'group'>): DevOpsGroupId {
  return s.group ?? DEFAULT_GROUP;
}

/** Secciones del grupo, en el orden de DEVOPS_SECTIONS. */
export function sectionsOfGroup(sections: DevOpsSection[], g: DevOpsGroupId): DevOpsSection[] {
  return (sections ?? []).filter((s) => groupOf(s) === g);
}

/** true si health[section.healthKey] !== true (idéntico al gate del outlet de DevOpsPage). */
export function isGated(
  s: Pick<DevOpsSection, 'healthKey'>,
  health: Record<string, unknown>,
): boolean {
  if (!s.healthKey) return false;
  return (health ?? {})[s.healthKey] !== true;
}

/** Partición para la barra: las gateadas salen de la fila primaria y van al desplegable.
 *  Regla: si TODAS las secciones de un grupo están gateadas, el grupo NO se oculta —
 *  se muestra atenuado (descubribilidad: el operador tiene que poder llegar al banner). */
export function partitionForBar(
  sections: DevOpsSection[],
  health: Record<string, unknown>,
): { visibleByGroup: Record<DevOpsGroupId, DevOpsSection[]>; gated: DevOpsSection[] } {
  const visibleByGroup = {
    resumen: [] as DevOpsSection[],
    operar: [] as DevOpsSection[],
    construir: [] as DevOpsSection[],
    gobernar: [] as DevOpsSection[],
    diagnosticar: [] as DevOpsSection[],
  } as Record<DevOpsGroupId, DevOpsSection[]>;
  const gated: DevOpsSection[] = [];
  (sections ?? []).forEach((s) => {
    if (isGated(s, health)) gated.push(s);
    else visibleByGroup[groupOf(s)].push(s);
  });
  return { visibleByGroup, gated };
}

/** Grupos para la primitiva Tabs (siempre los 4, con badge de cantidad si >1 visible). */
export function buildGroupTabs(groups: GroupDef[]): { id: string; label: string }[] {
  return (groups ?? []).map((g) => ({ id: g.id, label: g.label }));
}

/** Grupo que contiene a la sección activa (para que la fila primaria marque el correcto). */
export function activeGroupOf(sections: DevOpsSection[], activeId: string): DevOpsGroupId {
  const found = (sections ?? []).find((s) => s.id === activeId);
  return found ? groupOf(found) : 'resumen';
}

/** Línea de estado OPERACIONAL del header (reemplaza a buildAwareness del plan 119,
 *  que contaba flags). Ahora: servidor activo + estado del overview + último deploy.
 *  `overviewStatus` null ⇒ no se inventa nada: se omite el segmento. */
export function buildOperationalMeta(args: {
  selectedAlias: string | null;
  overviewStatus: 'ok' | 'warning' | 'danger' | 'unknown' | null;
  lastDeployAt: string | null;
  nowMs: number;
}): { text: string; tone: 'ok' | 'warn' | 'bad' | 'faint' }[] {
  const out: { text: string; tone: 'ok' | 'warn' | 'bad' | 'faint' }[] = [];
  if (args.selectedAlias) {
    out.push({ text: `Servidor: ${args.selectedAlias}`, tone: 'faint' });
  }
  if (args.overviewStatus !== null && args.overviewStatus !== undefined) {
    const mapa = {
      ok: { text: 'Sin novedades', tone: 'ok' as const },
      warning: { text: 'Requiere atención', tone: 'warn' as const },
      danger: { text: 'Hay algo roto', tone: 'bad' as const },
      unknown: { text: 'Sin datos suficientes', tone: 'faint' as const },
    };
    out.push(mapa[args.overviewStatus]);
  }
  if (args.lastDeployAt) {
    const ms = Date.parse(args.lastDeployAt);
    if (!Number.isNaN(ms)) {
      const dias = Math.floor((args.nowMs - ms) / 86_400_000);
      const cuando = dias <= 0 ? 'hoy' : dias === 1 ? 'ayer' : `hace ${dias} días`;
      out.push({ text: `Último despliegue: ${cuando}`, tone: 'faint' });
    }
  }
  return out;
}

/** Plan 239 F5.1 — Precedencia EXACTA (y en este orden):
 *  1. `subTab` de la URL, si es un id conocido y NO está gateado.
 *  2. `pinned` (localStorage), si es conocido y NO está gateado.
 *  3. 'resumen' si el cockpit está ON.
 *  4. primera sección NO gateada del array.
 *  5. 'pipelines' (último recurso, comportamiento histórico).
 *  Nunca devuelve un id gateado: aterrizar en un FlagGateBanner sería un aterrizaje roto. */
export function resolveLandingSection(args: {
  sections: DevOpsSection[];
  health: Record<string, unknown>;
  subTab: string | null;
  pinned: string | null;
  cockpitOn: boolean;
}): string {
  const { sections, health, subTab, pinned, cockpitOn } = args;
  const usable = (id: string | null): string | null => {
    if (!id) return null;
    const found = (sections ?? []).find((s) => s.id === id);
    if (!found || isGated(found, health)) return null;
    return found.id;
  };

  const porUrl = usable(subTab);
  if (porUrl) return porUrl;

  const porPin = usable(pinned);
  if (porPin) return porPin;

  if (cockpitOn) {
    const resumen = usable('resumen');
    if (resumen) return resumen;
  }

  const primeraLibre = (sections ?? []).find((s) => !isGated(s, health));
  if (primeraLibre) return primeraLibre.id;

  return 'pipelines';
}
