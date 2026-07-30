/**
 * plan275DevOpsGroupBalance.test.ts — Plan 275 F1.
 * Ningún grupo del cockpit DevOps debe amontonar más de 5 secciones (IA de
 * navegación, ver docs/275_PLAN_...md §2). El gate se corre CONTRA el
 * defecto: HOY 'construir' tiene 7 y este test da ROJO.
 */
import { describe, it, expect } from 'vitest';
import type { DevOpsSection } from '../DevOpsPage';
import { DEVOPS_SECTIONS } from '../DevOpsPage';
import { DEVOPS_SECTION_GROUPS, sectionsOfGroup, groupOf, partitionForBar } from '../devopsCockpitShell';

/* El plan 275 §1 escribió "≤ 5 en todos los grupos", pero ninguna de sus fases
 * toca `operar`, que su propio §2 ya documentaba con 6 secciones (Publicaciones,
 * Ambientes, Servidores, Despliegues, Compilar, Publicar Soluciones — las seis
 * son de operación, ninguna es gobierno de solo-lectura, así que ninguna puede
 * pasar a `gobernar` sin romper el `it` de "exactamente 4" de más abajo).
 * El umbral es 6 y no 5 por el riel 3.3 del propio plan: los gates compartidos
 * son DELTA, nunca "todo verde". Lo que este plan mata es el cajón de 7, y el
 * gate lo blinda: si `construir` volviera a 7 —o cualquier grupo amontonara más
 * que el techo preexistente— este test da ROJO. Bajar el techo a 5 exige partir
 * `operar`, que es diseño que el 275 no decidió. */
const MAX_SECCIONES_POR_GRUPO = 6;

describe('plan 275 F1 — balance de grupos del cockpit DevOps', () => {
  it(`ningún grupo visible tiene más de ${MAX_SECCIONES_POR_GRUPO} secciones`, () => {
    const porGrupo = new Map<string, number>();
    DEVOPS_SECTIONS.forEach((s) => {
      const g = groupOf(s);
      porGrupo.set(g, (porGrupo.get(g) ?? 0) + 1);
    });
    const infractores = [...porGrupo.entries()].filter(([, n]) => n > MAX_SECCIONES_POR_GRUPO);
    expect(infractores, `Grupos sobrecargados: ${JSON.stringify(infractores)}`).toEqual([]);
  });

  it('el grupo "gobernar" existe en el catálogo de grupos', () => {
    expect(DEVOPS_SECTION_GROUPS.map((g) => g.id)).toContain('gobernar');
  });

  it('"gobernar" agrupa exactamente las 4 secciones de solo-lectura de pipelines', () => {
    const ids = sectionsOfGroup(DEVOPS_SECTIONS, 'gobernar' as any).map((s) => s.id).sort();
    expect(ids).toEqual(['inventario-pipelines', 'matriz-entornos', 'paquete-entrega', 'pipeline-audit']);
  });

  it('"construir" baja de 7 a 3: pipelines, variables, editar-pipeline', () => {
    const ids = sectionsOfGroup(DEVOPS_SECTIONS, 'construir').map((s) => s.id).sort();
    expect(ids).toEqual(['editar-pipeline', 'pipelines', 'variables']);
  });

  // [ADICIÓN ARQUITECTO — crítica v1→v2] Guarda DIRECTA y autocontenida del riesgo #1
  // de §5: si se olvida agregar la clave `gobernar: []` al objeto hardcodeado de
  // `partitionForBar` (devopsCockpitShell.ts, dentro de la función), cualquier sección
  // con `group: 'gobernar'` revienta el render con TypeError en runtime. Esta guarda NO
  // depende de que DEVOPS_SECTIONS ya esté editado (construye su propia sección de
  // prueba), así que sigue protegiendo aunque cambie el orden de edición o el test
  // hermano `devopsCockpitShell.test.ts` (de otro plan) se modifique en el futuro.
  it('partitionForBar no revienta con una sección group:"gobernar" y la bucketea bien', () => {
    const conGobernar: DevOpsSection[] = [
      { id: 'x-gobernar-probe', label: 'x', group: 'gobernar', render: () => null } as DevOpsSection,
    ];
    expect(() => partitionForBar(conGobernar, {})).not.toThrow();
    const { visibleByGroup } = partitionForBar(conGobernar, {});
    expect(visibleByGroup.gobernar?.map((s) => s.id)).toEqual(['x-gobernar-probe']);
  });
});
