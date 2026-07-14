// Plan 122 F5 — tipos TS del contrato del núcleo del Comparador de BD (docs/122 §F1/§F2/§F3).
// Plan 124 — ampliado con el contrato de diff/run (doc 123 §F1/§F2) y el detalle completo de
// snapshot (doc 122 §F3, DbSnapshot) que 123/122 no exponen como tipos TS propios (123 es
// backend-puro; 122 F5 solo tipaba SnapshotMeta liviano para el listado). Todos los campos de
// acá fueron verificados 2026-07-14 contra el código real ya mergeado:
// `services/dbcompare_diff.py`, `services/dbcompare_runs.py`, `services/dbcompare_snapshot.py`.

export interface DbEnvironment {
  alias: string;
  engine: "sqlserver" | "oracle" | "sqlite";
  host: string;
  port: number;
  database: string;
  username: string;
  odbc_driver: string;
  schema_filter: string[] | null;
  notes: string;
  created_at: string;
  last_used_at: string | null;
  has_password: boolean;
  // [ADICIÓN ARQUITECTO] Plan 122 v2 — recencia de snapshot expuesta en GET /environments.
  latest_snapshot_taken_at: string | null;
  latest_snapshot_hash8: string | null;
}

export interface DriverInfo {
  module: string;
  available: boolean;
  install_hint: string;
}

export interface DriverStatus {
  sqlserver: DriverInfo;
  oracle: DriverInfo;
}

export interface SnapshotMeta {
  id: string;
  taken_at: string;
  duration_ms: number;
  counts: { tables: number; views: number; sequences: number; columns: number };
  content_hash: string;
}

export interface TestConnectionResult {
  ok: boolean;
  engine?: string;
  server_version?: string;
  latency_ms?: number;
  error?: string;
  install_hint?: string | null;
  likely_network?: boolean;
}

export interface DbCompareHealth {
  ok: boolean;
  flag_enabled: boolean;
  // Plan 126 F4 [FIX C5] — la UI lee este campo para mostrar/ocultar el
  // botón "Comparar datos…" sin llamar a un endpoint aparte.
  data_diff_enabled: boolean;
  keyring_available: boolean;
  drivers: DriverStatus;
}

// ---- Contrato de diff/run (doc 123 §F1/§F2, verificado contra services/dbcompare_diff.py y
// services/dbcompare_runs.py) — Plan 124 F1 ----

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

// ---- Detalle completo de snapshot (doc 122 §F3, GET /snapshots/<id>) — Plan 124 F1/F4/F5,
// verificado 1:1 contra services/dbcompare_snapshot.py:_reflect_table/_reflect_view ----

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

/** Snapshot COMPLETO (con schemas/tablas/columnas) — distinto de `SnapshotMeta` (liviano, sin
 * schemas, usado en el listado). Lo devuelve `GET /snapshots/<id>` y `POST .../snapshot`. */
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
