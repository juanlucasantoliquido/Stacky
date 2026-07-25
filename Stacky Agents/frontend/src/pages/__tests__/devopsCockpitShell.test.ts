/**
 * devopsCockpitShell.test.ts — Plan 239 F4/F5. Helpers puros, sin render.
 */
import { describe, it, expect } from 'vitest';
import {
  groupOf,
  sectionsOfGroup,
  isGated,
  partitionForBar,
  buildGroupTabs,
  activeGroupOf,
  buildOperationalMeta,
  resolveLandingSection,
  DEVOPS_SECTION_GROUPS,
  DEFAULT_GROUP,
  type DevOpsGroupId,
} from '../devopsCockpitShell';
import type { DevOpsSection } from '../DevOpsPage';

function sec(id: string, group?: DevOpsGroupId, healthKey?: string): DevOpsSection {
  return { id, label: id, group, healthKey, render: () => null } as DevOpsSection;
}

const SECTIONS: DevOpsSection[] = [
  sec('resumen', 'resumen', 'cockpit_enabled'),
  sec('pipelines', 'construir'),
  sec('despliegues', 'operar', 'deployments_enabled'),
  sec('variables', 'construir', 'variables_enabled'),
  sec('pr-review', 'diagnosticar', 'pr_reviewer_enabled'),
];

const TODO_ON = {
  cockpit_enabled: true,
  deployments_enabled: true,
  variables_enabled: true,
  pr_reviewer_enabled: true,
};

describe('F4 — agrupación', () => {
  it('sección sin group ⇒ DEFAULT_GROUP "operar" (contrato C20, KPI-10)', () => {
    expect(groupOf(sec('futura'))).toBe('operar');
    expect(DEFAULT_GROUP).toBe('operar');
  });

  it('DEVOPS_SECTION_GROUPS tiene exactamente 4 grupos (KPI-2)', () => {
    expect(DEVOPS_SECTION_GROUPS).toHaveLength(4);
  });

  it('sectionsOfGroup respeta el orden de DEVOPS_SECTIONS', () => {
    expect(sectionsOfGroup(SECTIONS, 'construir').map((s) => s.id)).toEqual(['pipelines', 'variables']);
  });

  it('isGated replica el gate del outlet (healthKey ausente ⇒ false)', () => {
    expect(isGated(sec('pipelines'), {})).toBe(false);
    expect(isGated(sec('x', 'operar', 'deployments_enabled'), {})).toBe(true);
    expect(isGated(sec('x', 'operar', 'deployments_enabled'), { deployments_enabled: true })).toBe(false);
  });

  it('partitionForBar saca las gateadas de visibleByGroup y las pone en gated', () => {
    const { visibleByGroup, gated } = partitionForBar(SECTIONS, { cockpit_enabled: true });
    expect(gated.map((s) => s.id).sort()).toEqual(['despliegues', 'pr-review', 'variables']);
    expect(visibleByGroup.construir.map((s) => s.id)).toEqual(['pipelines']);
    expect(visibleByGroup.resumen.map((s) => s.id)).toEqual(['resumen']);
  });

  it('grupo con TODAS gateadas ⇒ el grupo sigue existiendo (no se oculta)', () => {
    const { visibleByGroup } = partitionForBar(SECTIONS, {});
    expect(Object.keys(visibleByGroup).sort()).toEqual(
      ['construir', 'diagnosticar', 'operar', 'resumen'],
    );
    expect(visibleByGroup.diagnosticar).toEqual([]);
    expect(buildGroupTabs(DEVOPS_SECTION_GROUPS)).toHaveLength(4);
  });

  it('buildGroupTabs devuelve 4 items con id/label', () => {
    const tabs = buildGroupTabs(DEVOPS_SECTION_GROUPS);
    expect(tabs).toHaveLength(4);
    tabs.forEach((t) => {
      expect(typeof t.id).toBe('string');
      expect(typeof t.label).toBe('string');
    });
  });

  it("activeGroupOf('despliegues') ⇒ 'operar'; id inexistente ⇒ 'resumen'", () => {
    expect(activeGroupOf(SECTIONS, 'despliegues')).toBe('operar');
    expect(activeGroupOf(SECTIONS, 'no-existe')).toBe('resumen');
  });
});

describe('F4 — meta operacional', () => {
  it('overviewStatus null omite el segmento de estado (no inventa)', () => {
    const segs = buildOperationalMeta({
      selectedAlias: 'PF01', overviewStatus: null, lastDeployAt: null, nowMs: Date.now(),
    });
    const textos = segs.map((s) => s.text).join(' | ');
    expect(textos).toContain('PF01');
    expect(textos).not.toContain('Sin novedades');
    expect(textos).not.toContain('Sin datos suficientes');
  });

  it('NO menciona "capacidades" (el ruido del plan 119 se fue)', () => {
    const segs = buildOperationalMeta({
      selectedAlias: 'PF01', overviewStatus: 'ok',
      lastDeployAt: '2026-07-24T10:00:00Z', nowMs: Date.parse('2026-07-25T10:00:00Z'),
    });
    expect(segs.map((s) => s.text).join(' ')).not.toContain('capacidades');
  });
});

describe('F5 — resolveLandingSection', () => {
  const base = { sections: SECTIONS, health: TODO_ON, subTab: null, pinned: null, cockpitOn: true };

  it("sin nada + cockpitOn ⇒ 'resumen' (KPI-1)", () => {
    expect(resolveLandingSection(base)).toBe('resumen');
  });

  it("con subTab 'despliegues' ⇒ 'despliegues' (KPI-5)", () => {
    expect(resolveLandingSection({ ...base, subTab: 'despliegues' })).toBe('despliegues');
  });

  it("con subTab desconocido ⇒ cae a 'resumen'", () => {
    expect(resolveLandingSection({ ...base, subTab: 'no-existe' })).toBe('resumen');
  });

  it('con subTab GATEADO ⇒ NO lo devuelve (cae al siguiente)', () => {
    const health = { ...TODO_ON, deployments_enabled: false };
    expect(resolveLandingSection({ ...base, health, subTab: 'despliegues' })).toBe('resumen');
  });

  it("con pinned 'variables' y sin subTab ⇒ 'variables'", () => {
    expect(resolveLandingSection({ ...base, pinned: 'variables' })).toBe('variables');
  });

  it('subTab GANA a pinned', () => {
    expect(resolveLandingSection({ ...base, subTab: 'despliegues', pinned: 'variables' }))
      .toBe('despliegues');
  });

  it("con cockpitOff y sin nada ⇒ primera NO gateada, nunca 'resumen' (KPI-9)", () => {
    const health = { ...TODO_ON, cockpit_enabled: false };
    expect(resolveLandingSection({ ...base, health, cockpitOn: false })).toBe('pipelines');
  });

  it("con todo gateado ⇒ 'pipelines'", () => {
    const soloGateadas = SECTIONS.filter((s) => s.healthKey);
    expect(resolveLandingSection({
      sections: soloGateadas, health: {}, subTab: null, pinned: null, cockpitOn: true,
    })).toBe('pipelines');
  });
});
