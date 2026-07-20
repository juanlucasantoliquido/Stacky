// Plan 180 — Puente diff->repo: tipos espejo del payload del backend
// (api/db_compare_repo.py + services/dbcompare_repo_scripts.py). Claves EXACTAS
// del backend. NO editar dbcompareTypes.ts (lo toca el 176).

export type RepoTruncatedReason = "max_files" | "budget" | null;

export interface RepoScriptEntry {
  path: string;
  ticket: string | null;
  tables: string[];
  tables_qualified: string[];
  mtime: number;
  size_bytes: number;
  sha256_12: string;
}

export interface RepoScriptIndex {
  version: number;
  workspace_root: string;
  generated_at: string;
  globs: string[];
  files_scanned: number;
  truncated: boolean;
  truncated_reason: RepoTruncatedReason;
  scan_duration_ms: number;
  dirs_pruned: number;
  scripts: RepoScriptEntry[];
}

export type RepoMatchedBy = "SCHEMA.TABLE" | "TABLE";

export interface RepoCoverageCandidate {
  path: string;
  ticket: string | null;
  mtime: number;
  matched_by: RepoMatchedBy;
}

export interface RepoCoverageItem {
  object_type: string | null;
  schema: string | null;
  name: string | null;
  action: string | null;
  severity: string | null;
  candidates: RepoCoverageCandidate[];
}

export interface RepoCoverage {
  items: RepoCoverageItem[];
  covered_count: number;
  total_count: number;
}
