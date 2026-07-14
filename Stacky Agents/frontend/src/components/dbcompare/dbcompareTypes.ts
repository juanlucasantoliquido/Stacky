// Plan 122 F5 — tipos TS del contrato del núcleo del Comparador de BD (docs/122 §F1/§F2/§F3).

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
  keyring_available: boolean;
  drivers: DriverStatus;
}
