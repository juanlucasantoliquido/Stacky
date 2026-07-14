/**
 * Tests F5 (Plan 126) — dataDiffLogic: lógica PURA (sin React) de la paridad
 * de datos del Comparador de BD.
 */
import { describe, it, expect } from 'vitest';
import {
  buildDataGridRows,
  dataCounters,
  candidateFilter,
  type DataDiff,
  type DataCandidate,
} from '../dataDiffLogic';

function kpi1DataDiff(): DataDiff {
  // Mismo fixture KPI-1 del backend (Plan 126 F2 / doc §1): origen
  // (1,'A',1.5),(2,'B',2.0),(3,'C',3.0); destino (1,'A',1.5),(2,'B-mod',2.0),(4,'D',4.0).
  return {
    version: 1,
    schema: 'main',
    table: 'PARAMS',
    pk_cols: ['ID'],
    columns: ['ID', 'NOMBRE', 'VALOR'],
    column_types: { ID: 'INTEGER', NOMBRE: 'TEXT', VALOR: 'REAL' },
    columns_skipped: [],
    only_source: [{ ID: '3', NOMBRE: 'C', VALOR: '3' }],
    only_target: [{ ID: '4', NOMBRE: 'D', VALOR: '4' }],
    changed: [{ pk: { ID: '2' }, cells: { NOMBRE: { source: 'B', target: 'B-mod' } } }],
    row_counts: { source: 3, target: 3 },
    truncated: false,
    identical: false,
  };
}

describe('buildDataGridRows', () => {
  it('ordena changed, only_source, only_target', () => {
    const rows = buildDataGridRows(kpi1DataDiff());
    expect(rows.map((r) => r.kind)).toEqual(['changed', 'only_source', 'only_target']);
  });

  it('formatea el pk como col=val', () => {
    const rows = buildDataGridRows(kpi1DataDiff());
    expect(rows[0].pk).toBe('ID=2');
    expect(rows[1].pk).toBe('ID=3');
    expect(rows[2].pk).toBe('ID=4');
  });

  it('la fila changed trae la celda exacta con changed=true', () => {
    const rows = buildDataGridRows(kpi1DataDiff());
    const changedRow = rows[0];
    expect(changedRow.cells).toEqual([{ col: 'NOMBRE', source: 'B', target: 'B-mod', changed: true }]);
  });

  it('only_source: source poblado, target null, changed false', () => {
    const rows = buildDataGridRows(kpi1DataDiff());
    const onlySourceRow = rows.find((r) => r.kind === 'only_source')!;
    expect(onlySourceRow.cells).toEqual([
      { col: 'ID', source: '3', target: null, changed: false },
      { col: 'NOMBRE', source: 'C', target: null, changed: false },
      { col: 'VALOR', source: '3', target: null, changed: false },
    ]);
  });

  it('only_target: target poblado, source null', () => {
    const rows = buildDataGridRows(kpi1DataDiff());
    const onlyTargetRow = rows.find((r) => r.kind === 'only_target')!;
    expect(onlyTargetRow.cells.every((c) => c.source === null)).toBe(true);
    expect(onlyTargetRow.cells.find((c) => c.col === 'ID')!.target).toBe('4');
  });

  it('pk compuesto se junta con " · "', () => {
    const diff: DataDiff = {
      ...kpi1DataDiff(),
      pk_cols: ['ID', 'SUBID'],
      changed: [
        {
          pk: { ID: '2', SUBID: '9' },
          cells: { NOMBRE: { source: 'B', target: 'B-mod' } },
        },
      ],
      only_source: [],
      only_target: [],
    };
    const rows = buildDataGridRows(diff);
    expect(rows[0].pk).toBe('ID=2 · SUBID=9');
  });
});

describe('dataCounters', () => {
  it('cuenta inserts/updates/deletes del fixture KPI-1', () => {
    expect(dataCounters(kpi1DataDiff())).toEqual({ inserts: 1, updates: 1, deletes: 1 });
  });

  it('todo en cero si identical', () => {
    const diff: DataDiff = { ...kpi1DataDiff(), only_source: [], only_target: [], changed: [], identical: true };
    expect(dataCounters(diff)).toEqual({ inserts: 0, updates: 0, deletes: 0 });
  });
});

describe('candidateFilter', () => {
  function candidates(): DataCandidate[] {
    return [
      { schema: 'dbo', table: 'RCONTROLES', has_pk: true, estimated_columns: 3, comparable: true, reason: '', row_count_source: 10, row_count_target: 10 },
      { schema: 'dbo', table: 'RIDIOMA', has_pk: true, estimated_columns: 2, comparable: true, reason: '', row_count_source: 5, row_count_target: 5 },
      { schema: 'log', table: 'AUDITORIA', has_pk: false, estimated_columns: 4, comparable: false, reason: 'sin PK', row_count_source: null, row_count_target: null },
    ];
  }

  it('sin texto devuelve todas', () => {
    expect(candidateFilter(candidates(), '')).toHaveLength(3);
  });

  it('filtra por nombre de tabla, case-insensitive', () => {
    const result = candidateFilter(candidates(), 'ridi');
    expect(result.map((c) => c.table)).toEqual(['RIDIOMA']);
  });

  it('filtra por nombre de schema, case-insensitive', () => {
    const result = candidateFilter(candidates(), 'LOG');
    expect(result.map((c) => c.table)).toEqual(['AUDITORIA']);
  });

  it('sin coincidencias devuelve vacío', () => {
    expect(candidateFilter(candidates(), 'zzz')).toEqual([]);
  });
});
