/**
 * DevOpsPage (Plan 87 F4 - Panel DevOps base)
 * Página contenedora extensible para todas las features DevOps.
 *
 * Contrato de extensión (§3.12 C20):
 * - Registro DEVOPS_SECTIONS declarativo con id/label/icon?/healthKey?/gateFlagKey?/gateMessage?/render(ctx)
 * - Shell agnóstico: gate por sección con FlagGateBanner, montaje persistente, barra con flexWrap
 * - Sumar una sección DevOps futura = 1 entrada + 1 componente, CERO cambios en este archivo
 *
 * Las secciones futuras (88/89/90+) heredan:
 * - Flag: STACKY_DEVOPS_<FEATURE>_ENABLED (categoría devops, 5 patas)
 * - Health: key aditiva <feature>_enabled
 * - Rutas: /api/devops/<feature>/...
 * - Persistencia: keys devops_<feature>__* en client_profile (riel GET→merge→PUT)
 */
import React, { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { DevOps } from '../api/endpoints';
import { FlagGateBanner } from '../components/devops/FlagGateBanner';
import { ConnectionHealthStrip } from '../components/devops/ConnectionHealthStrip'; // Plan 116
import styles from './DevOpsPage.module.css'; // Plan 119
import { DevOpsHeaderV2 } from './DevOpsHeaderV2'; // Plan 119
import { DevOpsTabsV2 } from './DevOpsTabsV2'; // Plan 119
import { readQueryParam } from '../utils/queryParams'; // Plan 129
import type { DevOpsGroupId } from './devopsCockpitShell'; // Plan 239
import { resolveLandingSection, buildOperationalMeta } from './devopsCockpitShell'; // Plan 239 F3.4/F4/F5.1
import { DevOpsCockpitNav } from './DevOpsCockpitNav'; // Plan 239 F4
import { useLocalStorageState } from '../hooks/useLocalStorageState'; // Plan 239 F5.3
import { parseRoute, serializeRoute } from '../services/routes'; // Plan 165 (reuso, sin tocarlo)

// Health con index signature para keys aditivas (plan 88/90)
export interface DevOpsHealth {
  flag_enabled: boolean;
  generator_enabled: boolean;
  trigger_enabled: boolean;
  publications_enabled?: boolean; // Plan 88 — sección Publicaciones
  environments_enabled?: boolean; // Plan 89 — sección Ambientes
  agent_enabled?: boolean; // Plan 90 — sección Agente DevOps
  servers_enabled?: boolean; // Plan 91 — sección Servidores
  rdp_available?: boolean; // Plan 91 — RDP disponible (Windows + keyring)
  doctor_enabled?: boolean; // Plan 96 — Doctor de pipelines
  variables_enabled?: boolean; // Plan 94 — sección Variables (caja fuerte)
  section_doctor_enabled?: boolean; // Plan 104 — doctores IA por sección
  remote_console_enabled?: boolean; // Plan 105 — Consola remota por servidor
  remote_target_enabled?: boolean; // Plan 108 — agente/ambientes anclados al servidor seleccionado
  pr_reviewer_enabled?: boolean; // Plan 110 — Revisor de PRs
  connection_doctor_enabled?: boolean; // Plan 116 — doctor de conexiones
  ui_v2_enabled?: boolean; // Plan 119 — shell minimalista
  deployments_enabled?: boolean; // Plan 120 — Centro de Despliegues
  deployments_execute_enabled?: boolean; // Plan 120 — ejecutar deploy/rollback
  deployments_ai_enabled?: boolean; // Plan 120 — diagnóstico IA de deploys fallidos
  local_doctor_enabled?: boolean; // Plan 127 — doctor local DevOps (IA local)
  cockpit_enabled?: boolean; // Plan 239 — cockpit DevOps
  pipeline_inventory_enabled?: boolean; // Plan 246 — Inventario de pipelines
  pipeline_audit_enabled?: boolean; // Plan 248 — Auditoría de pipelines
  pipeline_nl_edit_enabled?: boolean; // Plan 250 — Edición quirúrgica de pipelines
  pipeline_nl_edit_commit_enabled?: boolean; // Plan 250 — commit al repo real (default OFF)
  [k: string]: boolean | undefined; // Keys futuras aditivas
}

// Contexto que recibe cada sección
export interface DevOpsSectionContext {
  health: DevOpsHealth;
  refetchHealth: () => void;
  // Plan 91 — aditivo/opcional: scoping por servidor para secciones que lo consuman
  selectedServer?: { alias: string; host: string } | null;
  servers?: ServerSummary[];
  // Plan 120 F8 (C7 v2) — OPCIONAL/aditivo (mismo precedente que selectedServer,
  // plan 91): navegar a otra sub-tab del shell. Ausente en shells que aún no lo
  // propaguen (p.ej. plan 119) ⇒ el caller degrada sin romper.
  setActiveSection?: (id: string) => void;
  /** Plan 239 F6 — true si esta sección es la visible. Las secciones que sondean
   *  DEBEN gatear su refetchInterval con esto. Ausente ⇒ tratar como true
   *  (shells que no lo propaguen degradan al comportamiento de hoy). */
  visible?: boolean;
}

// Contrato de sección del registro (§3.12 C20)
export interface DevOpsSection {
  id: string; // slug único kebab-case (namespacing)
  label: string; // título de la sub-tab
  icon?: string; // opcional: string corto para la sub-tab
  healthKey?: string; // si health[healthKey] !== true → FlagGateBanner
  gateFlagKey?: string; // flag que el banner ofrece activar (requerido si hay healthKey)
  gateMessage?: string; // mensaje del banner (requerido si hay healthKey)
  group?: DevOpsGroupId; // Plan 239 — cluster de navegación. Ausente ⇒ DEFAULT_GROUP.
  summary?: string;      // Plan 239 — 1 línea para el header de sección (opcional).
  render: (ctx: DevOpsSectionContext) => React.ReactNode;
}

// Importar PipelineBuilderSection (F5)
import { PipelineBuilderSection } from '../components/devops/PipelineBuilderSection';
// Importar PublicationsSection (Plan 88 F5)
import { PublicationsSection } from '../components/devops/PublicationsSection';
// Importar EnvironmentsSection (Plan 89 F5)
import { EnvironmentsSection } from '../components/devops/EnvironmentsSection';
// Importar DevOpsAgentSection (Plan 90 F3)
import { DevOpsAgentSection } from '../components/devops/DevOpsAgentSection';
// Importar ServersSection (Plan 91 F5)
import { ServersSection } from '../components/devops/ServersSection';
import { DevOpsServers, type ServerSummary } from '../api/endpoints';
// Importar VariablesSection (Plan 94 F4)
import { VariablesSection } from '../components/devops/VariablesSection';
// Importar RemoteConsoleSection (Plan 105 F4)
import { RemoteConsoleSection } from '../components/devops/RemoteConsoleSection';
// Importar PrReviewerSection (Plan 110 F7)
import { PrReviewerSection } from '../components/devops/PrReviewerSection';
// Importar DeploymentsSection (Plan 120 F7)
import { DeploymentsSection } from '../components/devops/DeploymentsSection';
// Plan 201 — Taller de Compilación (.sln + build Release + artefactos descargables)
import { BuildWorkshopSection } from '../components/devops/BuildWorkshopSection';
// Importar DevOpsOverviewSection (Plan 239 F3)
import { DevOpsOverviewSection } from '../components/devops/DevOpsOverviewSection';
// Plan 246 — Inventario vivo de pipelines (read-only, multiproveedor)
import { PipelineInventorySection } from '../components/devops/PipelineInventorySection';
// Plan 248 — Auditoría de pipelines (read-only, SEC + OPT)
import { PipelineAuditPanel } from '../components/devops/PipelineAuditPanel';
// Importar PipelineEditNlPanel (Plan 250 F4)
import { PipelineEditNlPanel } from '../components/devops/PipelineEditNlPanel';

// Registro extensible de secciones DevOps
// Los planes 88/89 y features futuras agregan entradas aquí SIN refactor
export const DEVOPS_SECTIONS: DevOpsSection[] = [
  // Plan 239 — Resumen: aterrizaje del cockpit. healthKey cockpit_enabled ⇒ con la
  // flag OFF la pestaña se atenúa y el shell v2/v1 sigue aterrizando en Pipelines.
  {
    id: 'resumen',
    label: 'Resumen',
    group: 'resumen',
    summary: 'Estado de despliegues, CI y conexiones en una pantalla.',
    healthKey: 'cockpit_enabled',
    gateFlagKey: 'STACKY_DEVOPS_COCKPIT_ENABLED',
    gateMessage: 'El Resumen del panel DevOps necesita la flag STACKY_DEVOPS_COCKPIT_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <DevOpsOverviewSection ctx={ctx} />,
  },
  {
    id: 'pipelines',
    label: 'Pipelines',
    group: 'construir',
    render: (ctx) => <PipelineBuilderSection ctx={ctx} />,
  },
  {
    id: 'publicaciones',
    label: 'Publicaciones',
    group: 'operar',
    healthKey: 'publications_enabled',
    gateFlagKey: 'STACKY_DEVOPS_PUBLICATIONS_ENABLED',
    gateMessage: 'La sección Publicaciones necesita la flag STACKY_DEVOPS_PUBLICATIONS_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <PublicationsSection ctx={ctx} />,
  },
  {
    id: 'ambientes',
    label: 'Ambientes',
    group: 'operar',
    healthKey: 'environments_enabled',
    gateFlagKey: 'STACKY_DEVOPS_ENVIRONMENTS_ENABLED',
    gateMessage: 'La sección Ambientes necesita la flag STACKY_DEVOPS_ENVIRONMENTS_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <EnvironmentsSection ctx={ctx} />,
  },
  // Plan 90 — Agente DevOps interactivo multi-turno
  {
    id: 'agente',
    label: 'Agente DevOps',
    group: 'diagnosticar',
    icon: '🛠️',
    healthKey: 'agent_enabled',
    gateFlagKey: 'STACKY_DEVOPS_AGENT_ENABLED',
    gateMessage: 'El agente DevOps interactivo necesita su flag (categoría DevOps).',
    render: (ctx) => <DevOpsAgentSection ctx={ctx} />,
  },
  // Plan 91 — Registro de servidores DevOps
  {
    id: 'servidores',
    label: 'Servidores',
    group: 'operar',
    icon: '🖥️',
    healthKey: 'servers_enabled',
    gateFlagKey: 'STACKY_DEVOPS_SERVERS_ENABLED',
    gateMessage: 'La sección Servidores necesita su flag (categoría DevOps).',
    render: (ctx) => <ServersSection ctx={ctx} />,
  },
  // Plan 94 — Caja fuerte de variables del pipeline
  {
    id: 'variables',
    label: 'Variables',
    group: 'construir',
    icon: '🔒',
    healthKey: 'variables_enabled',
    gateFlagKey: 'STACKY_DEVOPS_VARIABLES_ENABLED',
    gateMessage: 'La sección Variables necesita la flag STACKY_DEVOPS_VARIABLES_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <VariablesSection ctx={ctx} />,
  },
  // Plan 105 — Consola remota por servidor
  {
    id: 'remote-console',
    label: 'Consola',
    group: 'diagnosticar',
    icon: '💻',
    healthKey: 'remote_console_enabled',
    gateFlagKey: 'STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED',
    gateMessage: 'La sección Consola remota necesita la flag STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <RemoteConsoleSection ctx={ctx} />,
  },
  // Plan 110 — Revisor de PRs (Haiku solo-lectura + modelo local)
  {
    id: 'pr-review',
    label: 'Revisor de PRs',
    group: 'diagnosticar',
    icon: '🔎',
    healthKey: 'pr_reviewer_enabled',
    gateFlagKey: 'STACKY_PR_REVIEWER_ENABLED',
    gateMessage: 'La sección Revisor de PRs necesita la flag STACKY_PR_REVIEWER_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <PrReviewerSection ctx={ctx} />,
  },
  // Plan 120 — Centro de Despliegues (deploy multi-destino, rollback 1-click, DORA local)
  {
    id: 'despliegues',
    label: 'Despliegues',
    group: 'operar',
    icon: '🚀',
    healthKey: 'deployments_enabled',
    gateFlagKey: 'STACKY_DEPLOYMENTS_ENABLED',
    gateMessage: 'La sección Despliegues necesita la flag STACKY_DEPLOYMENTS_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <DeploymentsSection ctx={ctx} />,
  },
  // Plan 201 — Taller de Compilación (detección .sln + build Release + artefactos)
  {
    id: 'taller-compilacion',
    label: 'Compilar',
    group: 'operar',
    icon: '🔨',
    healthKey: 'build_workshop_enabled',
    gateFlagKey: 'STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED',
    gateMessage: 'La sección Compilar necesita la flag STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <BuildWorkshopSection ctx={ctx} />,
  },
  // Plan 246 — Inventario vivo de pipelines (read-only, multiproveedor)
  {
    id: 'inventario-pipelines',
    label: 'Inventario',
    group: 'construir',
    icon: '📋',
    summary: 'Todas las pipelines del proyecto: registradas, huerfanas y sin archivo.',
    healthKey: 'pipeline_inventory_enabled',
    gateFlagKey: 'STACKY_PIPELINE_INVENTORY_ENABLED',
    gateMessage: 'La seccion Inventario necesita la flag STACKY_PIPELINE_INVENTORY_ENABLED (Configuracion → Arnes, categoria DevOps).',
    render: (ctx) => <PipelineInventorySection ctx={ctx} />,
  },
  // Plan 248 — Auditoría de pipelines: riesgos de seguridad y recomendaciones
  {
    id: 'pipeline-audit',
    label: 'Auditoría',
    group: 'construir',
    icon: '🛡️',
    summary: 'Riesgos de seguridad y malas prácticas de una pipeline que ya existe.',
    healthKey: 'pipeline_audit_enabled',
    gateFlagKey: 'STACKY_PIPELINE_AUDIT_ENABLED',
    gateMessage: 'La sección Auditoría necesita la flag STACKY_PIPELINE_AUDIT_ENABLED (Configuración → Arnés, categoría Épicas/ADO).',
    render: (ctx) => <PipelineAuditPanel ctx={ctx} />,
  },
  // Plan 250 — Editar una pipeline que YA existe (patch quirurgico, nunca re-render)
  {
    id: 'editar-pipeline',
    label: 'Editar pipeline',
    group: 'construir',
    icon: '✏️',
    summary: 'Cambia una pipeline existente sin perder sus comentarios: diff exacto y commit con confirmacion.',
    healthKey: 'pipeline_nl_edit_enabled',
    gateFlagKey: 'STACKY_PIPELINE_NL_EDIT_ENABLED',
    gateMessage: 'La seccion Editar pipeline necesita la flag STACKY_PIPELINE_NL_EDIT_ENABLED (Configuracion → Arnes, categoria Epicas/ADO).',
    render: (ctx) => <PipelineEditNlPanel ctx={ctx} />,
  },
];

export const DevOpsPage: React.FC<{ subTab?: string | null }> = ({ subTab = null }) => {
  const healthQuery = useQuery({
    queryKey: ['devops-health'],
    queryFn: () => DevOps.health(),
    retry: false,
  });

  // Plan 239 F5.3 — sección de inicio fijada por el operador (un solo localStorage,
  // sin backend ni config). NO es un sistema de vistas guardadas (eso es el plan 173).
  const [pinned, setPinned] = useLocalStorageState<string | null>('stacky.devops.pinnedSection', null);

  // NOTA (plan 239 C1): `activeId` NO se inicializa con resolveLandingSection — el
  // aterrizaje lo aplica el efecto `landingApplied` de F3.4, que espera a que
  // healthQuery.data exista.
  const [activeId, setActiveId] = useState(DEVOPS_SECTIONS[0].id);
  // C10 - Montaje persistente: las secciones NUNCA se desmontan (display:none)
  const [mountedIds, setMountedIds] = useState<Set<string>>(new Set([DEVOPS_SECTIONS[0].id]));

  // Plan 91 F6 — servidores para el selector de scoping (solo si la flag ON: KPI-3).
  const serversQuery = useQuery({
    queryKey: ['devops-servers'],
    queryFn: () => DevOpsServers.list(),
    retry: false,
    enabled: healthQuery.data?.servers_enabled === true,
  });
  const [selectedAlias, setSelectedAlias] = useState<string | null>(
    () => localStorage.getItem('stacky.devops.selectedServer'),
  );
  const onSelectServer = (alias: string | null) => {
    setSelectedAlias(alias);
    if (alias) localStorage.setItem('stacky.devops.selectedServer', alias);
    else localStorage.removeItem('stacky.devops.selectedServer');
  };

  // Plan 129 — deep-link receptor: ?server=<alias> preselecciona el servidor
  // al montar (una sola vez, cuando la lista de servidores ya cargó). Reusa
  // selectedAlias/onSelectServer ya existentes (Plan 91 F6). Si el alias no
  // existe en la lista, se ignora en silencio.
  const appliedServerDeepLink = useRef(false);
  useEffect(() => {
    if (appliedServerDeepLink.current) return;
    if (!serversQuery.data) return;
    appliedServerDeepLink.current = true;
    const raw = readQueryParam('server');
    if (!raw) return;
    const exists = (serversQuery.data.servers ?? []).some((s) => s.alias === raw);
    if (exists) onSelectServer(raw);
  }, [serversQuery.data]);

  // C8 — LITERAL: si el alias persistido ya no existe, es null (no crashear).
  const selected = (serversQuery.data?.servers ?? []).find((s) => s.alias === selectedAlias) ?? null;

  // Al cambiar de sub-tab, marcar como montada (C10)
  const handleTabClick = (id: string) => {
    setActiveId(id);
    setMountedIds((prev) => new Set([...prev, id]));
  };

  // Plan 239 F3.4 — aterrizaje resuelto una sola vez, con la salud REAL en la mano.
  // Usa handleTabClick (no setActiveId) a propósito: es el único lugar que mantiene
  // la invariante C10 "activeId ∈ mountedIds".
  // NO va en un useState(() => …): el inicializador perezoso corre en el PRIMER
  // render, cuando healthQuery.data todavía es undefined, y no vuelve a correr ⇒
  // el cockpit ON aterrizaría igual en pipelines (KPI-1 fallaría en silencio).
  const landingApplied = useRef(false);
  useEffect(() => {
    if (landingApplied.current) return;
    if (!healthQuery.data) return;            // esperar la salud; jamás adivinarla
    landingApplied.current = true;
    handleTabClick(resolveLandingSection({
      sections: DEVOPS_SECTIONS,
      health: healthQuery.data as Record<string, unknown>,
      subTab,                                  // F5.2 — prop viva de la URL
      pinned,                                  // F5.3 — sección de inicio fijada
      cockpitOn: healthQuery.data.cockpit_enabled === true,
    }));
  }, [healthQuery.data]);

  // Plan 239 F5.3 (a) — prop VIVA: popstate / navegación in-app cambian subTab ⇒
  // seguirlo, sin pisar el click local (patrón lastApplied de SettingsPage.tsx:164).
  const lastAppliedSub = useRef(subTab);
  useEffect(() => {
    if (subTab !== lastAppliedSub.current) {
      lastAppliedSub.current = subTab;
      if (subTab && DEVOPS_SECTIONS.some((s) => s.id === subTab)) handleTabClick(subTab);
    }
  }, [subTab]);

  // Plan 239 F5.3 (b) — write-back: la sección elegida por click se refleja en el path
  // con replaceState (no pushState: no ensucia el historial, criterio del plan 165 F3 [A2]).
  // GUARD obligatorio: solo si la ruta actual es /devops (si el operador ya navegó a otra
  // tab, esta página puede estar desmontándose y reescribiría una URL ajena).
  useEffect(() => {
    const current = parseRoute(window.location.pathname, window.location.search);
    if (current.tab !== 'devops') return;
    const next = serializeRoute({ ...current, subtab: activeId });
    const target = window.location.pathname + window.location.search;
    if (next !== target) window.history.replaceState({}, '', next);
  }, [activeId]);

  const ctx: DevOpsSectionContext = {
    health: healthQuery.data ?? { flag_enabled: false, generator_enabled: false, trigger_enabled: false },
    refetchHealth: () => healthQuery.refetch(),
    selectedServer: selected ? { alias: selected.alias, host: selected.host } : null,
    servers: serversQuery.data?.servers ?? [],
    setActiveSection: handleTabClick, // Plan 120 F8 (C7 v2) — precedente selectedServer (plan 91)
  };

  // Plan 119 — shell v2 (presentación pura, conmutado por flag; ahora default ON).
  const uiV2 = ctx.health.ui_v2_enabled === true;
  // Plan 239 — cockpit (nav agrupada de 2 niveles + control de inicio fijable).
  const cockpit = ctx.health.cockpit_enabled === true;

  // Plan 239 F4 — estado operacional para el header. MISMA queryKey que usa la
  // sección Resumen con sus filtros por default ⇒ react-query comparte la entrada
  // de caché y NO se dispara una segunda request en el caso común. Sin sondeo
  // propio: el latido lo pone la sección cuando es la visible (F6).
  const overviewQuery = useQuery({
    queryKey: ['devops-overview', null, null, 14],
    queryFn: () => DevOps.overview({ appId: null, project: null, windowDays: 14 }),
    retry: false,
    enabled: cockpit,
  });

  if (healthQuery.isLoading) {
    return <div style={{ padding: '20px' }}>Cargando salud DevOps...</div>;
  }

  if (healthQuery.isError) {
    return (
      <div style={{ padding: '20px', color: 'red' }}>
        Error al cargar salud DevOps: {healthQuery.error instanceof Error ? healthQuery.error.message : ' desconocido'}
      </div>
    );
  }

  return (
    <div
      className={uiV2 ? styles.page : undefined}
      style={uiV2 ? undefined : { padding: '20px', height: '100%', display: 'flex', flexDirection: 'column' }}
    >
      {uiV2 ? (
        <DevOpsHeaderV2
          health={ctx.health}
          servers={ctx.servers ?? []}
          serversEnabled={ctx.health.servers_enabled === true}
          selectedAlias={selectedAlias}
          onSelectServer={onSelectServer}
          // Plan 239 F4 — con el cockpit ON la línea de contexto pasa a ser OPERACIONAL
          // (estado real) en vez de "N / 10 capacidades activas" (que contaba flags).
          meta={cockpit ? buildOperationalMeta({
            selectedAlias,
            overviewStatus: overviewQuery.data?.status ?? null,
            lastDeployAt: overviewQuery.data?.kpis?.last_deploy_at ?? null,
            nowMs: Date.now(),
          }) : undefined}
          // Plan 239 F5 — "Fijar como inicio": un solo localStorage, sin backend.
          actions={cockpit ? (
            <button
              type="button"
              className={styles.pinBtn}
              onClick={() => setPinned(activeId === pinned ? null : activeId)}
              title="Elegí en qué sección querés aterrizar al abrir DevOps"
            >
              {activeId === pinned ? 'Inicio fijado' : 'Fijar como inicio'}
            </button>
          ) : undefined}
        />
      ) : (
        <h2 style={{ marginTop: 0 }}>DevOps</h2>
      )}

      {/* Plan 116 — tira de salud de conexiones. INTOCABLE: NO condicionar a uiV2 (Plan 119 fix C1). */}
      {ctx.health.connection_doctor_enabled === true && (
        <ConnectionHealthStrip onGotoSection={handleTabClick} />
      )}

      {/* Barra de sub-tabs — escalera de 3 ramas (plan 239 F4.4):
          cockpit ⇒ DevOpsCockpitNav (2 niveles); si no, DevOpsTabsV2 del plan 119;
          si no, la barra inline v1. El outlet (C10) y ConnectionHealthStrip NO se tocan. */}
      {cockpit ? (
        <DevOpsCockpitNav sections={DEVOPS_SECTIONS} activeId={activeId} onSelect={handleTabClick} health={ctx.health} />
      ) : uiV2 ? (
        <DevOpsTabsV2 sections={DEVOPS_SECTIONS} activeId={activeId} onSelect={handleTabClick} health={ctx.health} />
      ) : (
        <div role="tablist" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
          {DEVOPS_SECTIONS.map((s) => (
            <button
              key={s.id}
              role="tab"
              aria-selected={activeId === s.id}
              aria-controls={`devops-panel-${s.id}`}
              onClick={() => handleTabClick(s.id)}
              disabled={!ctx.health.flag_enabled}
              style={{
                padding: '8px 16px',
                backgroundColor: activeId === s.id ? '#007bff' : '#6c757d',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: ctx.health.flag_enabled ? 'pointer' : 'not-allowed',
                opacity: ctx.health.flag_enabled ? 1 : 0.5,
              }}
            >
              {s.icon ? `${s.icon} ` : ''}
              {s.label}
            </button>
          ))}
          {/* Plan 91 F6 — selector de servidor activo (scoping aditivo). Plan 119: SOLO en v1 (en v2 vive en el header). */}
          {!uiV2 && ctx.health.servers_enabled === true && (ctx.servers?.length ?? 0) >= 1 && (
            <select
              value={selectedAlias ?? ''}
              onChange={(e) => onSelectServer(e.target.value || null)}
              style={{ padding: '8px', marginLeft: 'auto' }}
              title="Servidor activo para las secciones que lo usen"
            >
              <option value="">— ninguno —</option>
              {(ctx.servers ?? []).map((s) => (
                <option key={s.alias} value={s.alias}>{s.alias}</option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* Render de secciones con gate declarativo (C20) */}
      {DEVOPS_SECTIONS.map((s) => {
        // Solo renderizar secciones montadas
        // Plan 239 F3.4 — invariante: la sección ACTIVA siempre se renderiza, la
        // monte quien la monte. Sin esto, cualquier camino que fije activeId sin
        // pasar por handleTabClick (deep-link, pin, aterrizaje) deja el panel en blanco.
        if (!mountedIds.has(s.id) && s.id !== activeId) return null;

        // Gate declarativo: si healthKey !== true, mostrar FlagGateBanner
        const isGated = s.healthKey && ctx.health[s.healthKey] !== true;
        // Plan 239 F6 — ctx POR SECCIÓN: `visible` es true solo para la activa.
        // Las secciones ocultas dejan de sondear sin perder el montaje (C10).
        const sectionCtx: DevOpsSectionContext = { ...ctx, visible: activeId === s.id };
        const content = isGated ? (
          <FlagGateBanner
            flagKey={s.gateFlagKey!}
            flagLabel={s.label}
            message={s.gateMessage!}
            onEnabled={ctx.refetchHealth}
          />
        ) : (
          s.render(sectionCtx)
        );

        return (
          <div
            key={s.id}
            id={`devops-panel-${s.id}`}
            role="tabpanel"
            style={{ display: activeId === s.id ? 'block' : 'none' }}
          >
            {content}
          </div>
        );
      })}
    </div>
  );
};
