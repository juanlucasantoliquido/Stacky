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
  [k: string]: boolean | undefined; // Keys futuras: agent_enabled, etc.
}

// Contexto que recibe cada sección
export interface DevOpsSectionContext {
  health: DevOpsHealth;
  refetchHealth: () => void;
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
  // Plan 90 (agente DevOps):
  // {
  //   id: 'agente',
  //   label: 'Agente',
  //   icon: '🤖',
  //   healthKey: 'agent_enabled',
  //   gateFlagKey: 'STACKY_DEVOPS_AGENT_ENABLED',
  //   gateMessage: 'El Agente DevOps necesita su flag (categoría DevOps).',
  //   render: (ctx) => <AgentSection ctx={ctx} />,
  // },
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

  const ctx: DevOpsSectionContext = {
    health: healthQuery.data ?? { flag_enabled: false, generator_enabled: false, trigger_enabled: false },
    refetchHealth: () => healthQuery.refetch(),
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
