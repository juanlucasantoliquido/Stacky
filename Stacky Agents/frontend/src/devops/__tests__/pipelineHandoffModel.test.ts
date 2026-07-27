import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import {
  automaticActions,
  blockedReason,
  frontierSummary,
  manualActions,
  verdictLabel,
  type FrontierAction,
  type FrontierVerdict,
} from '../pipelineHandoffModel';

const act = (id: string, effective: FrontierVerdict): FrontierAction => ({
  id,
  label: `Acción ${id}`,
  effective,
  reason: 'porque sí',
  probe_detail: '',
});

const muestra: FrontierAction[] = [
  act('a', 'CAN'),
  act('b', 'CAN'),
  act('c', 'CANNOT'),
  act('d', 'CANNOT_NOW'),
  act('e', 'UNKNOWN'),
];

describe('plan 252 F5 — modelo puro del paquete de entrega', () => {
  it('1. automaticActions son sólo las CAN', () => {
    expect(automaticActions(muestra).map((a) => a.id)).toEqual(['a', 'b']);
  });

  it('2. manualActions y automaticActions son una partición exacta', () => {
    const auto = automaticActions(muestra);
    const man = manualActions(muestra);
    expect(auto.length + man.length).toBe(muestra.length);
    expect(auto.map((a) => a.id).filter((id) => man.some((m) => m.id === id))).toEqual([]);
  });

  it('3. UNKNOWN cuenta como trabajo del operador, nunca como resuelto', () => {
    expect(manualActions(muestra).map((a) => a.id)).toContain('e');
    expect(automaticActions(muestra).map((a) => a.id)).not.toContain('e');
  });

  it('4. frontierSummary es el titular de una línea', () => {
    expect(frontierSummary(muestra)).toBe('Stacky resuelve 2 de 5; 3 quedan para vos.');
    expect(frontierSummary([])).toContain('Todavía no se consultó');
    expect(frontierSummary([act('a', 'CAN')])).toContain('no te queda nada');
    expect(frontierSummary([act('a', 'CAN'), act('b', 'CANNOT')])).toContain('1 queda para vos');
  });

  it('5. verdictLabel distingue "hoy no" de "nunca"', () => {
    expect(verdictLabel('CAN')).toBe('Lo hace Stacky');
    expect(verdictLabel('CANNOT')).toBe('Lo hacés vos');
    expect(verdictLabel('CANNOT_NOW')).toBe('Lo hacés vos por ahora');
    expect(verdictLabel('UNKNOWN')).toBe('Lo hacés vos (Stacky no pudo verificarlo)');
  });

  it('6. blockedReason explica por qué no se puede pedir el paquete', () => {
    expect(blockedReason({ flagOn: true, yamlCount: 1 })).toBeNull();
    expect(blockedReason({ flagOn: false, yamlCount: 1 })).toContain(
      'STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED',
    );
    expect(blockedReason({ flagOn: true, yamlCount: 0 })).toContain('ningún archivo');
  });

  it('7. los helpers son puros y no mutan la entrada', () => {
    const antes = muestra.map((a) => a.id);
    automaticActions(muestra);
    manualActions(muestra);
    expect(muestra.map((a) => a.id)).toEqual(antes);
  });

  it('8. el panel se monta por DEVOPS_SECTIONS y no hand-rollea su gate', () => {
    const raiz = join(__dirname, '..', '..');
    const page = readFileSync(join(raiz, 'pages', 'DevOpsPage.tsx'), 'utf-8');
    expect(page).toContain("id: 'paquete-entrega'");
    expect(page).toContain("healthKey: 'handoff_bundle_enabled'");
    expect(page).toContain("gateFlagKey: 'STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED'");

    const panel = readFileSync(
      join(raiz, 'components', 'devops', 'PipelineHandoffPanel.tsx'),
      'utf-8',
    );
    expect(panel).not.toContain('style={{');
  });
});
