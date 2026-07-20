// Plan 139 — modelo de navegación del App Shell v2 (PURO: sin React, sin CSS).

// Debe coincidir 1:1 con `type Tab` de App.tsx. Si App.tsx agrega/quita un tab,
// actualizar aquí (el test shellNav.test.ts detecta el drift de cobertura).
export type ShellTab =
  | "team" | "tickets" | "review" | "unblocker" | "pm" | "logs"
  | "settings" | "docs" | "memory" | "diagnostics" | "history"
  | "migrador" | "devops" | "dbcompare" | "costcenter" | "planes"
  | "evolution";

export interface ShellTabMeta {
  label: string;
  iconName: string; // clave de ICON_BY_NAME (ver shellIcons.ts)
}

export const TAB_META: Record<ShellTab, ShellTabMeta> = {
  team:        { label: "Mi Equipo",     iconName: "Zap" },
  tickets:     { label: "Tickets ADO",   iconName: "ClipboardList" },
  review:      { label: "Revisión",      iconName: "Inbox" },
  unblocker:   { label: "Desatascador",  iconName: "Wrench" },
  pm:          { label: "PM",            iconName: "LayoutDashboard" },
  logs:        { label: "System Logs",   iconName: "ScrollText" },
  history:     { label: "Historial",     iconName: "History" },
  diagnostics: { label: "Diagnóstico",   iconName: "Stethoscope" },
  docs:        { label: "Docs",          iconName: "FileText" },
  memory:      { label: "Memoria",       iconName: "Brain" },
  devops:      { label: "DevOps",        iconName: "Server" },
  migrador:    { label: "Migrador",      iconName: "ArrowRightLeft" },
  dbcompare:   { label: "Comparador BD", iconName: "Database" },
  costcenter:  { label: "Centro de Costos", iconName: "DollarSign" },
  planes:      { label: "Planes",        iconName: "Compass" },
  evolution:   { label: "Evolución",     iconName: "Dna" },
  settings:    { label: "Configuración", iconName: "Settings" },
};

export interface ShellNavGroup {
  id: string;
  label: string;
  tabs: ShellTab[];
}

export const SHELL_NAV_GROUPS: ShellNavGroup[] = [
  { id: "trabajo",        label: "Trabajo",        tabs: ["team", "tickets", "review", "unblocker"] },
  { id: "observabilidad", label: "Observabilidad", tabs: ["pm", "logs", "history", "diagnostics", "costcenter", "planes", "evolution"] },
  { id: "conocimiento",   label: "Conocimiento",   tabs: ["docs", "memory"] },
  { id: "plataforma",     label: "Plataforma",     tabs: ["devops", "migrador", "dbcompare"] },
  { id: "configuracion",  label: "Configuración",  tabs: ["settings"] },
];

export interface VisibilityInput {
  sections: { team: boolean; pm: boolean; logs: boolean; docs: boolean; memory: boolean };
  migradorEnabled: boolean;
  devopsEnabled: boolean;
  dbCompareEnabled: boolean;
  costCenterEnabled: boolean;
  planesEnabled: boolean;
  evolutionEnabled: boolean;
}

// Tabs SIEMPRE visibles (espejo del render actual de App.tsx: no dependen de gate).
// "team" (Mi Equipo) NO está acá: es ocultable y default oculto (ver sections.team).
const ALWAYS_VISIBLE: ReadonlyArray<ShellTab> = [
  "tickets", "review", "unblocker", "settings", "diagnostics", "history",
];

export function computeVisibleTabs(input: VisibilityInput): Set<ShellTab> {
  const v = new Set<ShellTab>(ALWAYS_VISIBLE);
  if (input.sections.team) v.add("team");
  if (input.sections.pm) v.add("pm");
  if (input.sections.logs) v.add("logs");
  if (input.sections.docs) v.add("docs");
  if (input.sections.memory) v.add("memory");
  if (input.migradorEnabled) v.add("migrador");
  if (input.devopsEnabled) v.add("devops");
  if (input.dbCompareEnabled) v.add("dbcompare");
  if (input.costCenterEnabled) v.add("costcenter");
  if (input.planesEnabled) v.add("planes");
  if (input.evolutionEnabled) v.add("evolution");
  return v;
}

export function orderedVisibleGroups(visible: ReadonlySet<ShellTab>): ShellNavGroup[] {
  return SHELL_NAV_GROUPS
    .map((g) => ({ ...g, tabs: g.tabs.filter((t) => visible.has(t)) }))
    .filter((g) => g.tabs.length > 0);
}

export const SIDEBAR_COLLAPSED_KEY = "stacky.ui.shell.collapsed";

export function parseCollapsed(raw: string | null): boolean {
  return raw === "true";
}
