/**
 * Tests F6 (Plan 125) — scriptsLogic: logica PURA (sin React) de la tab
 * "Scripts" del Comparador de BD. Ver doc 125 v2 F6 / NOTA C1: esta es la
 * parte que NO depende de DbComparePage (Plan 122/124, ausente en este
 * checkout) y por eso se implementa y testea completa.
 */
import { describe, it, expect } from 'vitest';
import { buildScriptRows, pairingBadge, type Manifest, type ScriptPairRow } from '../scriptsLogic';

function manifestConTresGrupos(): Manifest {
  return {
    version: 1,
    run_id: 'run_test_001',
    generated_at: '2026-07-14T12:00:00Z',
    engine: 'sqlserver',
    source_alias: 'DEV',
    target_alias: 'TEST',
    entries: [
      {
        seq: 901,
        file: '09_destructivo/901_column_removed_dbo_CLIENTES.sql',
        action: 'column_removed',
        object_type: 'table',
        schema: 'dbo',
        name: 'CLIENTES',
        destructive: true,
        modifies_table: true,
        backup_file: '01_backups/001_table_backup_dbo_CLIENTES.sql',
        rollback_file: null,
      },
      {
        seq: 201,
        file: '02_paridad/201_table_added_dbo_NUEVA.sql',
        action: 'table_added',
        object_type: 'table',
        schema: 'dbo',
        name: 'NUEVA',
        destructive: false,
        modifies_table: false,
        backup_file: null,
        rollback_file: null,
      },
      {
        seq: 202,
        file: '02_paridad/202_index_removed_dbo_CLIENTES.sql',
        action: 'index_removed',
        object_type: 'table',
        schema: 'dbo',
        name: 'CLIENTES',
        destructive: false,
        modifies_table: true,
        backup_file: null,
        rollback_file: '01_backups/003_rollback_index_removed_dbo_CLIENTES.sql',
      },
      {
        seq: 902,
        file: '09_destructivo/902_table_removed_dbo_VIEJA.sql',
        action: 'table_removed',
        object_type: 'table',
        schema: 'dbo',
        name: 'VIEJA',
        destructive: true,
        modifies_table: true,
        backup_file: '01_backups/002_table_backup_dbo_VIEJA.sql',
        rollback_file: '01_backups/004_rollback_table_removed_dbo_VIEJA.sql',
      },
    ],
    counts: { backups: 4, parity: 2, destructive: 2 },
  };
}

describe('buildScriptRows - Plan 125 F6', () => {
  it('ordena por seq ascendente sin importar el orden del manifest', () => {
    const rows = buildScriptRows(manifestConTresGrupos());
    expect(rows.map((r) => r.seq)).toEqual([201, 202, 901, 902]);
  });

  it('deriva el grupo del prefijo de file (paridad/destructivo)', () => {
    const rows = buildScriptRows(manifestConTresGrupos());
    const byAction = Object.fromEntries(rows.map((r) => [r.action, r]));
    expect(byAction.table_added.grupo).toBe('paridad');
    expect(byAction.index_removed.grupo).toBe('paridad');
    expect(byAction.column_removed.grupo).toBe('destructivo');
    expect(byAction.table_removed.grupo).toBe('destructivo');
  });

  it('deriva grupo "backup" para un file bajo 01_backups/', () => {
    const rows = buildScriptRows({
      ...manifestConTresGrupos(),
      entries: [
        {
          seq: 1,
          file: '01_backups/001_table_backup_dbo_CLIENTES.sql',
          action: 'table_backup',
          object_type: 'table',
          schema: 'dbo',
          name: 'CLIENTES',
          destructive: false,
          modifies_table: false,
          backup_file: null,
          rollback_file: null,
        },
      ],
    });
    expect(rows[0].grupo).toBe('backup');
  });

  it('objectLabel combina schema.name', () => {
    const rows = buildScriptRows(manifestConTresGrupos());
    expect(rows.find((r) => r.action === 'table_added')?.objectLabel).toBe('dbo.NUEVA');
  });

  it('manifest vacio -> lista vacia', () => {
    expect(buildScriptRows({ ...manifestConTresGrupos(), entries: [] })).toEqual([]);
  });
});

describe('pairingBadge - Plan 125 F6', () => {
  const base: ScriptPairRow = {
    seq: 1,
    file: 'x',
    action: 'x',
    objectLabel: 'dbo.X',
    destructive: false,
    backupFile: null,
    rollbackFile: null,
    grupo: 'paridad',
  };

  it('1. solo backup -> "backup"', () => {
    expect(pairingBadge({ ...base, backupFile: '01_backups/001.sql' })).toBe('backup');
  });

  it('2. solo rollback -> "rollback"', () => {
    expect(pairingBadge({ ...base, rollbackFile: '01_backups/002.sql' })).toBe('rollback');
  });

  it('3. backup + rollback -> "backup+rollback"', () => {
    expect(pairingBadge({ ...base, backupFile: '01_backups/001.sql', rollbackFile: '01_backups/002.sql' })).toBe(
      'backup+rollback',
    );
  });

  it('4. ninguno -> "sin resguardo (aditivo)"', () => {
    expect(pairingBadge(base)).toBe('sin resguardo (aditivo)');
  });
});
