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
import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { DevOps } from '../api/endpoints';
import { FlagGateBanner } from '../components/devops/FlagGateBanner';

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
  [k: string]: boolean | undefined; // Keys futuras aditivas
}

// Contexto que recibe cada sección
export interface DevOpsSectionContext {
  health: DevOpsHealth;
  refetchHealth: () => void;
  // Plan 91 — aditivo/opcional: scoping por servidor para secciones que lo consuman
  selectedServer?: { alias: string; host: string } | null;
  servers?: ServerSummary[];
}

// Contrato de sección del registro (§3.12 C20)
export interface DevOpsSection {
  id: string; // slug único kebab-case (namespacing)
  label: string; // título de la sub-tab
  icon?: string; // opcional: string corto para la sub-tab
  healthKey?: string; // si health[healthKey] !== true → FlagGateBanner
  gateFlagKey?: string; // flag que el banner ofrece activar (requerido si hay healthKey)
  gateMessage?: string; // mensaje del banner (requerido si hay healthKey)
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

// Registro extensible de secciones DevOps
// Los planes 88/89 y features futuras agregan entradas aquí SIN refactor
export const DEVOPS_SECTIONS: DevOpsSection[] = [
  {
    id: 'pipelines',
    label: 'Pipelines',
    render: (ctx) => <PipelineBuilderSection ctx={ctx} />,
  },
  {
    id: 'publicaciones',
    label: 'Publicaciones',
    healthKey: 'publications_enabled',
    gateFlagKey: 'STACKY_DEVOPS_PUBLICATIONS_ENABLED',
    gateMessage: 'La sección Publicaciones necesita la flag STACKY_DEVOPS_PUBLICATIONS_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <PublicationsSection ctx={ctx} />,
  },
  {
    id: 'ambientes',
    label: 'Ambientes',
    healthKey: 'environments_enabled',
    gateFlagKey: 'STACKY_DEVOPS_ENVIRONMENTS_ENABLED',
    gateMessage: 'La sección Ambientes necesita la flag STACKY_DEVOPS_ENVIRONMENTS_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <EnvironmentsSection ctx={ctx} />,
  },
  // Plan 90 — Agente DevOps interactivo multi-turno
  {
    id: 'agente',
    label: 'Agente DevOps',
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
    icon: '🖥️',
    healthKey: 'servers_enabled',
    gateFlagKey: 'STACKY_DEVOPS_SERVERS_ENABLED',
    gateMessage: 'La sección Servidores necesita su flag (categoría DevOps).',
    render: (ctx) => <ServersSection ctx={ctx} />,
  },
];

export const DevOpsPage: React.FC = () => {
  const healthQuery = useQuery({
    queryKey: ['devops-health'],
    queryFn: () => DevOps.health(),
    retry: false,
  });

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

  // C8 — LITERAL: si el alias persistido ya no existe, es null (no crashear).
  const selected = (serversQuery.data?.servers ?? []).find((s) => s.alias === selectedAlias) ?? null;

  const ctx: DevOpsSectionContext = {
    health: healthQuery.data ?? { flag_enabled: false, generator_enabled: false, trigger_enabled: false },
    refetchHealth: () => healthQuery.refetch(),
    selectedServer: selected ? { alias: selected.alias, host: selected.host } : null,
    servers: serversQuery.data?.servers ?? [],
  };

  // Al cambiar de sub-tab, marcar como montada (C10)
  const handleTabClick = (id: string) => {
    setActiveId(id);
    setMountedIds((prev) => new Set([...prev, id]));
  };

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
    <div style={{ padding: '20px', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <h2 style={{ marginTop: 0 }}>DevOps</h2>

      {/* Barra de sub-tabs - C20 flexWrap para soportar 5+ secciones */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
        {DEVOPS_SECTIONS.map((s) => (
          <button
            key={s.id}
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
        {/* Plan 91 F6 — selector de servidor activo (scoping aditivo) */}
        {ctx.health.servers_enabled === true && (ctx.servers?.length ?? 0) >= 1 && (
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

      {/* Render de secciones con gate declarativo (C20) */}
      {DEVOPS_SECTIONS.map((s) => {
        // Solo renderizar secciones montadas
        if (!mountedIds.has(s.id)) return null;

        // Gate declarativo: si healthKey !== true, mostrar FlagGateBanner
        const isGated = s.healthKey && ctx.health[s.healthKey] !== true;
        const content = isGated ? (
          <FlagGateBanner
            flagKey={s.gateFlagKey!}
            flagLabel={s.label}
            message={s.gateMessage!}
            onEnabled={ctx.refetchHealth}
          />
        ) : (
          s.render(ctx)
        );

        return (
          <div
            key={s.id}
            style={{ display: activeId === s.id ? 'block' : 'none' }}
          >
            {content}
          </div>
        );
      })}
    </div>
  );
};
