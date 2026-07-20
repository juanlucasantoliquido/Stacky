// Plan 178 — Tipos del radar de ambientes (espejo EXACTO del payload de api/db_compare_watch.py).
// NO se edita dbcompareTypes.ts (lo toca el 176); estos tipos viven aparte.

export interface BySeverity {
  info: number;
  warn: number;
  danger: number;
}

export type RadarState = "green" | "amber" | "red";

export interface RadarCell {
  source_alias: string;
  target_alias: string;
  state: RadarState;
  by_severity: BySeverity;
  parity_score: number | null;
  run_id: string;
  finished_at: string | null;
  initiated_by: string;
  watched: boolean;
}

export interface RadarEnvironment {
  alias: string;
  engine: string;
  has_baseline: boolean;
}

export interface WatchSummary {
  by_severity: BySeverity;
  parity_score: number;
}

export interface WatchEntry {
  watch_id: string;
  source_alias: string;
  target_alias: string;
  enabled: boolean;
  created_at: string;
  last_attempt_at: string | null;
  last_run_id: string | null;
  last_done_run_id: string | null;
  last_harvested_run_id: string | null;
  last_summary: WatchSummary | null;
  consecutive_errors: number;
}

export type DriftEventKind =
  | "drift_new"
  | "drift_worse"
  | "drift_cleared"
  | "baseline_violation"
  | "watch_error";

export interface DriftEvent {
  event_id: string;
  kind: DriftEventKind;
  watch_id: string | null;
  source_alias: string | null;
  target_alias: string | null;
  run_id: string | null;
  created_at: string;
  read: boolean;
  detail: Record<string, unknown>;
}

export interface BaselineEntry {
  version: number;
  alias: string;
  snapshot_id: string;
  pinned_at: string;
  note: string;
  last_alerted_content_hash: string | null;
  broken: boolean;
}

export interface RadarPayload {
  ok: boolean;
  environments: RadarEnvironment[];
  cells: RadarCell[];
  watches: WatchEntry[];
  unread_events: number;
}
