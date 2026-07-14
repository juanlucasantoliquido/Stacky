/**
 * scriptsLogic.ts — Plan 125 F6.
 *
 * Logica PURA (sin React) de la tab "Scripts" del Comparador de BD: arma
 * las filas de la tabla de pareo backup<->paridad a partir del manifest
 * generado por el backend (services/dbcompare_scripts.py F3) y calcula el
 * badge de pareo por fila. No hace fetch ni toca el DOM.
 *
 * NOTA C1 (doc 125 v2): esta pieza NO depende de DbComparePage (Plan
 * 122/124) — por eso se implementa completa aunque ScriptsPanel/SqlViewer
 * (que si montan dentro de esa pagina) queden como gap documentado.
 */

export interface ManifestEntry {
  seq: number;
  file: string;
  action: string;
  object_type: string;
  schema: string;
  name: string;
  destructive: boolean;
  modifies_table: boolean;
  backup_file: string | null;
  rollback_file: string | null;
}

export interface Manifest {
  version: number;
  run_id: string;
  generated_at: string;
  engine: string;
  source_alias: string;
  target_alias: string;
  entries: ManifestEntry[];
  counts: { backups: number; parity: number; destructive: number };
}

export type ScriptGrupo = 'backup' | 'paridad' | 'destructivo';

export interface ScriptPairRow {
  seq: number;
  file: string;
  action: string;
  objectLabel: string;
  destructive: boolean;
  backupFile: string | null;
  rollbackFile: string | null;
  grupo: ScriptGrupo;
}

export type PairingBadge = 'backup' | 'rollback' | 'backup+rollback' | 'sin resguardo (aditivo)';

function grupoFromFile(file: string): ScriptGrupo {
  if (file.startsWith('01_backups/')) return 'backup';
  if (file.startsWith('09_destructivo/')) return 'destructivo';
  return 'paridad';
}

export function buildScriptRows(manifest: Manifest): ScriptPairRow[] {
  return [...manifest.entries]
    .sort((a, b) => a.seq - b.seq)
    .map((entry) => ({
      seq: entry.seq,
      file: entry.file,
      action: entry.action,
      objectLabel: `${entry.schema}.${entry.name}`,
      destructive: entry.destructive,
      backupFile: entry.backup_file,
      rollbackFile: entry.rollback_file,
      grupo: grupoFromFile(entry.file),
    }));
}

export function pairingBadge(row: ScriptPairRow): PairingBadge {
  if (row.backupFile && row.rollbackFile) return 'backup+rollback';
  if (row.backupFile) return 'backup';
  if (row.rollbackFile) return 'rollback';
  return 'sin resguardo (aditivo)';
}
