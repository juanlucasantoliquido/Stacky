/**
 * Plan 215 F7 — Modelo PURO del Publicador de Soluciones.
 *
 * Sin render, sin fetch: solo transformaciones testeables sobre los contratos
 * que devuelve `backend/api/devops_solution_publisher.py`. La sección queda
 * como render puro sobre estos helpers.
 */

/** Config por solución — espejo EXACTO de `publish_config_store.default_config()`. */
export interface PublishConfig {
  mode: "auto" | "dotnet_publish" | "msbuild_pubxml" | "build_only";
  configuration: string;
  project_csproj: string | null;
  publish_profile: string | null;
  extra_args: string[];
  register_as_deploy_app: boolean;
  updated_at: string | null;
}

/** Plan efectivo — espejo de `publish_profile_scanner.resolve_publish_plan()`. */
export interface PublishPlan {
  mode_effective: string;
  supported: boolean;
  reason: string;
  target: string;
  argv_tail: string[];
}

export interface PublisherProject {
  name: string;
  csproj_path: string;
  type: string;
}

export interface PublishProfileEntry {
  name: string;
  method: string;
  csproj_path: string;
}

/** Solución del catálogo YA enriquecida por el endpoint (`_enrich`). */
export interface PublisherSolution {
  slug: string;
  sln_path: string;
  friendly_name: string;
  tracked: boolean;
  missing: boolean;
  origin?: "scan" | "manual";
  projects: PublisherProject[];
  config: PublishConfig;
  plan: PublishPlan;
  publish_profiles: PublishProfileEntry[];
}

/** Estados posibles de un run de publish (incluye `interrupted` del ledger). */
export type PublishRunStatus =
  | "running"
  | "success"
  | "failed"
  | "cancelled"
  | "toolchain_missing"
  | "unsupported"
  | "interrupted";

export const PUBLISH_MODES: PublishConfig["mode"][] = [
  "auto",
  "dotnet_publish",
  "msbuild_pubxml",
  "build_only",
];

const _MODE_LABEL: Record<string, string> = {
  auto: "Automático",
  dotnet_publish: "dotnet publish (proyecto SDK-style)",
  msbuild_pubxml: "MSBuild + perfil .pubxml (.NET Framework)",
  build_only: "Solo compilar (sin publicar)",
};

export function publishModeLabel(mode: string): string {
  return _MODE_LABEL[mode] ?? mode;
}

/**
 * ¿Se puede publicar esta solución ahora mismo?
 * El `.sln` tiene que existir, el plan tiene que ser soportado y la máquina
 * tiene que tener toolchain. Cualquier dato faltante ⇒ false (nunca lanza).
 */
export function canPublish(sol: PublisherSolution, toolchainAvailable: boolean): boolean {
  if (!sol) return false;
  return !sol.missing && Boolean(sol.plan?.supported) && Boolean(toolchainAvailable);
}

const _STATUS_LABEL: Record<PublishRunStatus, string> = {
  running: "Publicando…",
  success: "Publicado",
  failed: "Falló",
  cancelled: "Cancelado",
  toolchain_missing: "Falta toolchain .NET",
  unsupported: "No soportado",
  interrupted: "Interrumpido (backend reiniciado)",
};

export function publishStatusLabel(s: PublishRunStatus): string {
  return _STATUS_LABEL[s] ?? String(s);
}

/**
 * Texto del comando previsto, SOLO como evidencia para el confirm del operador.
 * Nunca se ejecuta: el backend arma el argv como lista (jamás una cadena de shell).
 */
export function commandPreview(argv: string[]): string {
  return (argv || [])
    .map((a) => {
      const s = String(a ?? "");
      return /\s/.test(s) ? `"${s}"` : s;
    })
    .join(" ");
}

const _REASON_LABEL: Record<string, string> = {
  requiere_dotnet_sdk:
    "Falta el SDK de .NET en esta máquina: instalalo y volvé a abrir la sección.",
  requiere_msbuild:
    "Falta MSBuild (Build Tools de Visual Studio) en esta máquina: instalalo y reintentá.",
  sin_pubxml_filesystem:
    "El proyecto no tiene un perfil de publicación a carpeta local: creá uno en Visual Studio o elegí el modo «Solo compilar».",
  pubxml_remoto_no_soportado:
    "El perfil publica a un destino remoto (MSDeploy/FTP): Stacky solo publica a carpeta local. Para desplegar usá el Centro de Despliegues.",
  pubxml_no_encontrado:
    "No se encontró el perfil elegido en el proyecto: revisá la configuración de esta solución.",
  toolchain_missing:
    "Falta el toolchain de compilación (.NET o MSBuild) en esta máquina.",
  // Presente en el backend (`devops_solution_publisher._enrich`) aunque el plan
  // no lo listaba: sin esta entrada el operador veía el código crudo.
  plan_no_resoluble:
    "No se pudo resolver el plan de publicación para esta solución: revisá que el .sln y sus proyectos se lean bien.",
};

export function planReasonLabel(reason: string): string {
  if (!reason) return "";
  return _REASON_LABEL[reason] ?? reason;
}

/**
 * Extrae rutas `.sln` de un texto libre (lo que devuelve el agente DevOps o lo
 * que pega el operador). Limpia viñetas, numeración y comillas; deduplica sin
 * distinguir mayúsculas (Windows). La frontera agéntico→estado sigue siendo el
 * import validado en el servidor: esto solo PRELLENA el formulario.
 */
export function parseSolutionPathsFromText(text: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of String(text ?? "").split(/\r?\n/)) {
    let line = raw.trim();
    line = line.replace(/^[-*•]+\s*/, "").replace(/^\d+[.)]\s*/, "");
    line = line.trim().replace(/^["'`]+/, "").replace(/["'`,;]+$/, "").trim();
    if (!line.toLowerCase().endsWith(".sln")) continue;
    const key = line.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(line);
  }
  return out;
}

/** ¿La solución pide atención del operador (no publicable tal como está)? */
export function needsAttention(sol: PublisherSolution): boolean {
  if (!sol) return false;
  return Boolean(sol.missing) || !sol.plan?.supported;
}

/** Espejo del allowlist de `publish_config_store._EXTRA_ARG_RE` (máx 8 args). */
const _EXTRA_ARG_RE = /^[A-Za-z0-9/:=._,()\\-]{1,120}$/;
export const MAX_EXTRA_ARGS = 8;

export function isValidExtraArg(arg: string): boolean {
  return _EXTRA_ARG_RE.test(String(arg ?? ""));
}

/** El tamaño de artefacto usa el formateador canónico del repo (plan 161). */
export { formatBytes } from "../../services/format";
