// Plan 119 — helpers puros del shell DevOps v2 (sin dependencia de DOM/render).
export const CAPABILITY_KEYS = [
  'flag_enabled', 'servers_enabled', 'agent_enabled', 'rdp_available',
  'publications_enabled', 'environments_enabled', 'preflight_enabled',
  'variables_enabled', 'production_enabled', 'doctor_enabled',
] as const;

export function countCapabilities(health: Record<string, unknown>): { active: number; total: number } {
  const total = CAPABILITY_KEYS.length;
  const active = CAPABILITY_KEYS.reduce((n, k) => n + (health[k] === true ? 1 : 0), 0);
  return { active, total };
}

export type Tone = 'ok' | 'warn' | 'faint';
export interface AwarenessSegment { text: string; tone: Tone; }

export function buildAwareness(
  health: Record<string, unknown>,
  selectedAlias: string | null,
): AwarenessSegment[] {
  const { active, total } = countCapabilities(health);
  return [
    selectedAlias
      ? { text: `${selectedAlias} activo`, tone: 'ok' }
      : { text: 'sin servidor activo', tone: 'faint' },
    health.agent_enabled === true
      ? { text: 'agente disponible', tone: 'ok' }
      : { text: 'agente en espera', tone: 'faint' },
    health.rdp_available === true
      ? { text: 'RDP listo', tone: 'ok' }
      : { text: 'RDP no disponible', tone: 'faint' },
    { text: `${active} / ${total} capacidades activas`, tone: 'faint' },
  ];
}

export interface TabState { active: boolean; gated: boolean; }
// Debe coincidir EXACTAMENTE con el gate del outlet (DevOpsPage.tsx:266).
export function classifyTab(
  section: { id: string; healthKey?: string },
  health: Record<string, unknown>,
  activeId: string,
): TabState {
  return {
    active: section.id === activeId,
    gated: !!section.healthKey && health[section.healthKey] !== true,
  };
}
