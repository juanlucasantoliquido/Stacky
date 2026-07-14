// Plan 124 — Comparador de BD: tipos del explorador visual.
//
// PENDIENTE: este archivo es una interfaz AISLADA Y PROPIA de este plan (124), creada porque
// el cimiento del Plan 122 (registro de ambientes) y del Plan 123 (motor de diff) NO están
// mergeados en esta rama de trabajo (confirmado 2026-07-14: F0 del doc
// `Stacky Agents/docs/124_PLAN_DB_COMPARE_SECCION_INMERSIVA_EXPLORADOR_VISUAL.md` dio AUSENTE
// en los 3 chequeos). Cuando 122/123 se mergeen, reconciliar este archivo con
// `frontend/src/components/dbcompare/dbcompareTypes.ts` real (probablemente reemplazando este
// archivo por un import/re-export del real, o eliminándolo si los nombres ya coinciden 1:1).
// Los campos de acá son un espejo LITERAL de los contratos congelados citados en los docs
// 122 §F3 (snapshot) y 123 §F1/§F2 (diff/run).

// ---- Contrato de diff/run (doc 123 §F1/§F2) ----

export type Severity = "info" | "warn" | "danger";
export type DiffAction = "added" | "removed" | "changed";
export type ObjectType = "table" | "view" | "sequence";
export type RunPhase = "queued" | "snapshot_source" | "snapshot_target" | "diff" | "done";
export type RunStatus = "running" | "done" | "error";

export interface DiffChange {
  kind: string;
  severity: Severity;
  detail: Record<string, unknown>;
}

export interface DiffItem {
  object_type: ObjectType;
  schema: string;
  name: string;
  action: DiffAction;
  severity: Severity;
  changes: DiffChange[];
}

export interface DiffSummary {
  by_severity: Record<Severity, number>;
  by_action: Record<DiffAction, number>;
  by_object_type: Record<ObjectType, number>;
  objects_total: number;
  objects_unchanged: number;
  parity_score: number;
}

export interface SchemaDiffSide {
  alias: string;
  snapshot_id: string;
  content_hash: string;
}

export interface SchemaDiff {
  version: number;
  engine: string;
  source: SchemaDiffSide;
  target: SchemaDiffSide;
  items: DiffItem[];
  summary: DiffSummary;
}

export interface CompareRun {
  run_id: string;
  source_alias: string;
  target_alias: string;
  engine: string;
  mode: "fresh" | "cached";
  status: RunStatus;
  phase: RunPhase;
  started_at: string;
  finished_at: string | null;
  duration_ms: number;
  source_snapshot_id: string | null;
  target_snapshot_id: string | null;
  summary: DiffSummary | null;
  diff: SchemaDiff | null;
  error: string | null;
  stale?: boolean;
}

// ---- Contrato de ambientes (doc 122 §F1/§F4), mínimo consumido por el wizard ----

export interface DbEnvironment {
  alias: string;
  engine: string;
  host: string;
  port: number;
  database: string;
  username: string;
  has_password: boolean;
  latest_snapshot_taken_at: string | null;
  latest_snapshot_hash8: string | null;
}

// ---- Contrato de snapshot (doc 122 §F3) — [FIX C2 en crítica v2 del plan 124] ----

export interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  default: string | null;
  autoincrement: boolean;
}

export interface PrimaryKeyInfo {
  name: string | null;
  columns: string[];
}

export interface ForeignKeyInfo {
  name: string | null;
  columns: string[];
  referred_schema: string;
  referred_table: string;
  referred_columns: string[];
}

export interface IndexInfo {
  name: string | null;
  columns: string[];
  unique: boolean;
}

export interface UniqueConstraintInfo {
  name: string | null;
  columns: string[];
}

export interface CheckConstraintInfo {
  name: string | null;
  sqltext: string;
}

export interface TableSnapshot {
  columns: ColumnInfo[];
  primary_key: PrimaryKeyInfo;
  foreign_keys: ForeignKeyInfo[];
  indexes: IndexInfo[];
  unique_constraints: UniqueConstraintInfo[];
  check_constraints: CheckConstraintInfo[];
}

export interface ViewSnapshot {
  definition: string | null;
  definition_sha256: string | null;
  error: string | null;
}

export interface SchemaSnapshot {
  tables: Record<string, TableSnapshot>;
  views: Record<string, ViewSnapshot>;
  sequences: string[];
}

export interface DbSnapshot {
  version: number;
  id: string;
  alias: string;
  engine: string;
  taken_at: string;
  duration_ms: number;
  schemas: Record<string, SchemaSnapshot>;
  counts: { tables: number; views: number; sequences: number; columns: number };
  content_hash: string;
}
