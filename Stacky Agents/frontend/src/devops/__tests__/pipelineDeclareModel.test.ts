import { describe, expect, it } from 'vitest';

import {
  agruparSkipped,
  avisoContadorNoBaja,
  avisoMasking,
  resumenDeclaracion,
  type DeclarePlanView,
} from '../pipelineDeclareModel';

const plan = (items: DeclarePlanView['items'] = [], skipped: DeclarePlanView['skipped'] = []): DeclarePlanView => ({
  items,
  skipped,
  provider: 'azure_devops',
});

describe('plan 260 F6 — pipelineDeclareModel (puro)', () => {
  it('1. resumenDeclaracion dice cuantos nombres', () => {
    expect(resumenDeclaracion(plan([]))).not.toContain('undefined');
    expect(resumenDeclaracion(plan([{ key: 'A', secret: false, reason: 'x', note: '' }]))).toContain('1 nombre');
    expect(
      resumenDeclaracion(
        plan([
          { key: 'A', secret: false, reason: 'x', note: '' },
          { key: 'B', secret: true, reason: 'y', note: '' },
        ]),
      ),
    ).toContain('2 nombres');
  });

  it('2. skipped agrupado por motivo', () => {
    const p = plan(
      [],
      [
        { key: 'SERV', motivo: 'no es una variable' },
        { key: 'RUTA', motivo: 'es una ruta' },
        { key: 'SERV2', motivo: 'no es una variable' },
      ],
    );
    const agrupado = agruparSkipped(p);
    expect(agrupado.get('no es una variable')).toEqual(['SERV', 'SERV2']);
    expect(agrupado.get('es una ruta')).toEqual(['RUTA']);
  });

  it('3. (ADICIÓN 3) aviso contador no baja explica por qué eso es correcto', () => {
    const msg = avisoContadorNoBaja(2, 2);
    expect(msg).toContain('2');
    expect(msg.toLowerCase()).not.toContain('undefined');
  });

  it('3b. aviso contador detecta la anomalía si SI bajara (canario de producción)', () => {
    const msg = avisoContadorNoBaja(2, 1);
    expect(msg).toContain('Ojo');
  });

  it('4. (v2, C6) aviso de masking lista las keys que quedaron sin enmascarar', () => {
    expect(avisoMasking([])).toBe('');
    const msg = avisoMasking(['DB_PASSWORD', 'API_KEY']);
    expect(msg).toContain('DB_PASSWORD');
    expect(msg).toContain('API_KEY');
    expect(msg.toLowerCase()).toContain('secreta');
  });
});
