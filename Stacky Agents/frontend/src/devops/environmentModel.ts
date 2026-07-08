/**
 * environmentModel.ts — Plan 89 F5
 *
 * Tipos espejo del contrato backend (§4, services/environment_init.py) +
 * lógica pura del wizard de inicialización de ambientes. Sin React, sin I/O.
 * `validateSettingsLocal` es feedback INMEDIATO en UI; la fuente de verdad
 * sigue siendo el backend (api/client_profile.py F3).
 */

export type FolderKind = "entry" | "processing" | "output" | "default";

export interface EnvironmentSettings {
  environment_root: string;
  folder_layout: Record<FolderKind, string[]>;
  per_process_subfolder: boolean;
}

export type PlanEntryStatus = "to_create" | "exists_ok" | "conflict" | "unsafe";

export interface PlanEntry {
  path: string;
  status: PlanEntryStatus;
  reason: string | null;
}

export interface EnvironmentPlanResponse {
  root: string;
  root_exists: boolean;
  layout_fingerprint: string;
  entries: PlanEntry[];
  summary: Record<PlanEntryStatus, number>;
  sandbox_active?: boolean; // Plan 107
}

export interface EnvironmentApplyResponse {
  created: string[];
  skipped_existing: string[];
  conflicts: string[];
  unsafe: string[];
  failed: Array<{ path: string; error: string }>;
  ignored_not_in_layout: string[];
  sandbox_active?: boolean; // Plan 107
}

const _WINDOWS_RESERVED = new Set([
  "con", "prn", "aux", "nul",
  ...Array.from({ length: 9 }, (_, i) => `com${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `lpt${i + 1}`),
]);

const _INVALID_CHARS = /[<>:"|?*\x00-\x1f]/;

/**
 * emptyEnvironmentSettings — layout Pacífico como SUGERENCIA inicial editable
 * (no hardcode de backend: el operador puede borrar/editar todo).
 */
export function emptyEnvironmentSettings(): EnvironmentSettings {
  return {
    environment_root: "",
    folder_layout: {
      entry: ["IN_"],
      processing: ["productivas"],
      output: ["salida"],
      default: [],
    },
    per_process_subfolder: false,
  };
}

function isSafeSegmentLocal(seg: string): boolean {
  const s = (seg ?? "").trim();
  if (!s || s.startsWith("/") || s.startsWith("\\")) return false;
  // absoluta a simple vista (drive letter o UNC)
  if (/^[A-Za-z]:[\\/]/.test(s)) return false;
  const comps = s.split(/[\\/]+/);
  for (const comp of comps) {
    if (!comp || comp.includes("..")) return false;
    if (_INVALID_CHARS.test(comp)) return false;
    const base = comp.split(".")[0].toLowerCase();
    if (_WINDOWS_RESERVED.has(base)) return false;
    if (comp.endsWith(".") || comp.endsWith(" ")) return false;
  }
  return true;
}

/**
 * validateSettingsLocal — espejo de la validación F3 para feedback inmediato.
 * La fuente de verdad sigue siendo el backend.
 */
export function validateSettingsLocal(s: EnvironmentSettings): string[] {
  const errors: string[] = [];
  const root = s.environment_root ?? "";
  const looksAbsolute = /^[A-Za-z]:[\\/]|^\//.test(root);
  if (!root.trim() || !looksAbsolute) {
    errors.push("environment_root debe ser una ruta absoluta.");
  }
  const layout = s.folder_layout ?? ({} as Record<FolderKind, string[]>);
  for (const kind of Object.keys(layout) as FolderKind[]) {
    const segs = layout[kind] ?? [];
    for (const seg of segs) {
      if (!isSafeSegmentLocal(seg)) {
        errors.push(`folder_layout.${kind}: segmento invalido '${seg}'.`);
      }
    }
  }
  return errors;
}

/** summarizePlan — cuenta entries por status. */
export function summarizePlan(entries: PlanEntry[]): Record<PlanEntryStatus, number> {
  const summary: Record<PlanEntryStatus, number> = {
    to_create: 0,
    exists_ok: 0,
    conflict: 0,
    unsafe: 0,
  };
  for (const e of entries) {
    summary[e.status] += 1;
  }
  return summary;
}

/** selectablePaths — solo los paths en estado to_create (los únicos aplicables). */
export function selectablePaths(entries: PlanEntry[]): string[] {
  return entries.filter((e) => e.status === "to_create").map((e) => e.path);
}

/**
 * allExistsOk (ADICIÓN v3) — true si entries no está vacío y TODAS tienen
 * status === "exists_ok". Alimenta el badge "Ambiente verificado" post-apply.
 */
export function allExistsOk(entries: PlanEntry[]): boolean {
  return entries.length > 0 && entries.every((e) => e.status === "exists_ok");
}

/**
 * validateSandboxOverrideLocal (Plan 107 F5) — espejo del guard backend
 * (validate_sandbox_override) para feedback INMEDIATO en UI. NO es fuente de
 * verdad (el backend re-valida siempre, api/devops.py::_load_env_context).
 * Semántica por SEGMENTOS con frontera '/' (C2: nada de prefijo de string
 * crudo) y case-insensitive SIEMPRE (C9/G5: más estricto que POSIX; aceptable
 * porque el backend re-valida y Stacky corre Windows-first). No existe
 * validateRootLocal: el chequeo de "absoluta" reusa la MISMA regex de
 * validateSettingsLocal (línea ~91 de este archivo).
 */
export function validateSandboxOverrideLocal(override: string, productionRoot: string): string | null {
  const o = (override ?? "").trim();
  if (!o || !/^[A-Za-z]:[\\/]|^\//.test(o)) return "la raíz sandbox debe ser una ruta absoluta";
  // normaliza: separadores a '/', sin separadores finales (G9), lowercase (G5)
  const norm = (p: string) => p.trim().replace(/[\\/]+/g, "/").replace(/\/+$/, "").toLowerCase();
  const prod = (productionRoot ?? "").trim();
  if (!prod || !/^[A-Za-z]:[\\/]|^\//.test(prod)) return null; // sin producción válida no hay nada que pisar (G7)
  const a = norm(o);
  const b = norm(prod);
  if (a === b) return "sandbox_igual_a_produccion";
  if (a.startsWith(b + "/")) return "sandbox_dentro_de_produccion"; // frontera '/': G4 (C:\prod-test) NO matchea
  if (b.startsWith(a + "/")) return "produccion_dentro_de_sandbox";
  return null;
}
