/**
 * Plan 177 F5 — Modelo PURO del checkbox "Abrir PR" del board. Sin DOM
 * (testeable con vitest solo, respeta el gap RTL/jsdom). El checkbox viene
 * PREMARCADO por directiva del operador (2026-07-18): resolver una incidencia
 * abre un PR salvo que se desmarque.
 *
 * 2026-08-02 — se agrega el chequeo PREVIO de repositorio git y el resultado
 * visible del PR. Antes el control se ESCONDÍA entero cuando algo no estaba
 * (`shouldShowOpenPrCheckbox` devolvía false y no quedaba rastro), y el
 * resultado del PR sólo existía como comentario en la Issue del tracker: desde
 * Stacky el operador tildaba y nunca se enteraba de nada.
 */

export const DEFAULT_OPEN_PR = true; // premarcado

/**
 * @deprecated Usá `describeOpenPrControl`. Esta función ESCONDE el control
 * cuando la capacidad está apagada, que es indistinguible para el operador de
 * que la funcionalidad no exista — el defecto reportado el 2026-08-02. Se
 * conserva sólo para no romper consumidores externos.
 */
export function shouldShowOpenPrCheckbox(args: {
  canResolve: boolean;
  devPrEnabled: boolean;
}): boolean {
  return args.canResolve && args.devPrEnabled;
}

/** Respuesta de GET /api/incidents/dev-pr/preflight (200 siempre). */
export interface DevPrPreflight {
  ok: boolean;
  reason: string | null;
  message: string;
  warning: string | null;
  warning_message: string;
  repo_root: string | null;
  origin: string | null;
  workspace_root: string | null;
  tracker_type: string | null;
  /** `name` del provider que devolvió la fábrica del backend ("gitlab",
   * "azure_devops", …), NO un texto de presentación: el nombre bonito lo pone
   * `etiquetaProveedor` acá, para que el backend no duplique la lista. */
  provider_label: string | null;
  project: string | null;
}

const NOMBRES_PROVEEDOR: Record<string, string> = {
  gitlab: "GitLab",
  azure_devops: "Azure DevOps",
};

/** Nombre presentable del proveedor. Uno desconocido se muestra tal cual llegó
 *  (nunca se traga el dato por no tenerlo en la tabla). */
export function etiquetaProveedor(name: string | null | undefined): string | null {
  if (!name) return null;
  return NOMBRES_PROVEEDOR[name] ?? name;
}

export interface OpenPrControl {
  /** ¿Se dibuja el control? Sólo depende de que el ticket admita el resolutor. */
  visible: boolean;
  /** Deshabilitado = el PR NO puede salir; `motivo` dice por qué. */
  disabled: boolean;
  /** Valor efectivo del tilde (nunca true si está deshabilitado). */
  checked: boolean;
  /** Texto visible al lado del control. "" cuando no hay nada que explicar. */
  motivo: string;
  etiqueta: string;
}

const ESPERANDO = "Verificando el repositorio git del proyecto…";
const APAGADO =
  "El PR automático está apagado. Encendelo en Configuración → Flags " +
  "(STACKY_INCIDENT_DEV_PR_ENABLED).";

/**
 * Estado del tilde "Abrir PR" en el punto de lanzamiento del ticket.
 *
 * REGLA: el control nunca desaparece por una condición del entorno. Si el PR no
 * puede salir se muestra DESHABILITADO con el motivo a la vista — un control que
 * se esconde solo es indistinguible de una funcionalidad que no existe, que es
 * exactamente lo que reportó el operador.
 */
export function describeOpenPrControl(args: {
  canResolve: boolean;
  devPrEnabled: boolean;
  /** null = el chequeo previo todavía no volvió. */
  preflight: DevPrPreflight | null;
  /** Lo que el operador tildó. */
  deseado: boolean;
}): OpenPrControl {
  const base = { visible: true, etiqueta: "Abrir PR" };

  if (!args.canResolve) {
    return { ...base, visible: false, disabled: true, checked: false, motivo: "" };
  }
  if (!args.devPrEnabled) {
    return { ...base, disabled: true, checked: false, motivo: APAGADO };
  }
  if (args.preflight === null) {
    return { ...base, disabled: true, checked: false, motivo: ESPERANDO };
  }
  if (!args.preflight.ok) {
    return {
      ...base,
      disabled: true,
      checked: false,
      motivo: args.preflight.message || "No se puede abrir el PR automático.",
    };
  }
  const proveedor = etiquetaProveedor(args.preflight.provider_label);
  return {
    visible: true,
    disabled: false,
    checked: args.deseado,
    motivo: args.preflight.warning_message || "",
    etiqueta: proveedor ? `Abrir PR (${proveedor})` : "Abrir PR",
  };
}

/**
 * Preflight sintético para cuando el chequeo NO se pudo hacer (backend caído,
 * red). Se usa en vez de `null` porque `null` significa "todavía cargando" y
 * dejaría el control en "Verificando…" indefinidamente.
 */
export const PREFLIGHT_CAIDO: DevPrPreflight = {
  ok: false,
  reason: "sin_respuesta",
  message:
    "No se pudo verificar el repositorio git del proyecto (Stacky no respondió). " +
    "El PR automático queda deshabilitado hasta poder comprobarlo.",
  warning: null,
  warning_message: "",
  repo_root: null,
  origin: null,
  workspace_root: null,
  tracker_type: null,
  provider_label: null,
  project: null,
};

/** Default de la casilla: premarcada SOLO si el PR realmente puede salir. */
export function defaultOpenPr(preflight: DevPrPreflight | null): boolean {
  return DEFAULT_OPEN_PR && preflight?.ok === true;
}

// ── Vista de conjunto: TODOS los proyectos ───────────────────────────────────

/** Respuesta de GET /api/incidents/dev-pr/preflight-all (200 siempre). */
export interface DevPrPreflightAll {
  ok: boolean;
  projects: DevPrPreflight[];
  total: number;
  con_git: number;
  /** Estado de la capacidad, INDEPENDIENTE de si los repos están bien. */
  dev_pr_enabled: boolean;
  message: string;
}

export interface FilaDeRepo {
  project: string;
  estado: "con-git" | "sin-git";
  /** Motivo (si no anda) o aviso (si anda con reparo). "" si no hay nada que decir. */
  detalle: string;
  repoRoot: string | null;
  workspaceRoot: string | null;
  proveedor: string | null;
}

export interface ResumenDeRepos {
  filas: FilaDeRepo[];
  conGit: number;
  sinGit: number;
  error: string;
}

/**
 * Traduce el estado de todos los proyectos a algo mirable de un vistazo.
 * Los proyectos que NO andan van PRIMERO: son los únicos accionables.
 */
export function resumirEstadoDeRepos(data: DevPrPreflightAll | null): ResumenDeRepos {
  if (!data) return { filas: [], conGit: 0, sinGit: 0, error: "" };

  const filas: FilaDeRepo[] = (data.projects ?? []).map((p) => ({
    project: p.project ?? "(sin nombre)",
    estado: p.ok ? "con-git" : "sin-git",
    detalle: (p.ok ? p.warning_message : p.message) || "",
    repoRoot: p.repo_root,
    workspaceRoot: p.workspace_root,
    proveedor: etiquetaProveedor(p.provider_label),
  }));
  // Primero los rotos; dentro de cada grupo, alfabético (orden estable).
  filas.sort((a, b) => {
    if (a.estado !== b.estado) return a.estado === "sin-git" ? -1 : 1;
    return a.project.localeCompare(b.project);
  });

  return {
    filas,
    conGit: filas.filter((f) => f.estado === "con-git").length,
    sinGit: filas.filter((f) => f.estado === "sin-git").length,
    error: data.ok ? "" : data.message || "No se pudo verificar el estado de los proyectos.",
  };
}

/** Respuesta de GET /api/incidents/dev-pr/result/<execution_id> (200 siempre). */
export interface DevPrResultDTO {
  ok: boolean;
  found: boolean;
  status: string;
  terminal: boolean;
  execution_id: number;
  pr_url?: string;
  pr_id?: number;
  branch?: string;
  error?: string;
  files_committed?: string[];
}

export interface PrResultView {
  visible: boolean;
  tono: "ok" | "info" | "error" | "pendiente";
  texto: string;
  url: string | null;
}

const OCULTO: PrResultView = { visible: false, tono: "info", texto: "", url: null };

/** Traduce el resultado del auto-PR a algo que el operador pueda leer. */
export function describePrResult(r: DevPrResultDTO | null): PrResultView {
  if (!r || r.status === "no_solicitado") return OCULTO;

  switch (r.status) {
    case "pendiente":
      return {
        visible: true,
        tono: "pendiente",
        texto: "Se abrirá un Pull Request con el fix y los tests al terminar la ejecución.",
        url: null,
      };
    case "opened": {
      const id = r.pr_id != null ? `#${r.pr_id}` : "";
      const rama = r.branch ? ` desde \`${r.branch}\`` : "";
      return {
        visible: true,
        tono: "ok",
        texto: `Pull Request ${id} abierto${rama}.`.replace("  ", " "),
        url: r.pr_url || null,
      };
    }
    case "blocked_empty":
      return {
        visible: true,
        tono: "info",
        texto: "No se abrió PR: el agente no dejó cambios de código en el working tree.",
        url: null,
      };
    case "skipped":
      return {
        visible: true,
        tono: "info",
        texto: r.error || "No se abrió el PR automático.",
        url: null,
      };
    case "error":
      return {
        visible: true,
        tono: "error",
        texto: `No se pudo abrir el PR: ${r.error || "error desconocido"}`,
        url: null,
      };
    default:
      // Un `status` que este frontend no conoce (backend más nuevo) se muestra
      // igual: preferimos un texto crudo antes que tragarnos el resultado.
      return {
        visible: true,
        tono: "info",
        texto: `Estado del PR automático: ${r.status}`,
        url: r.pr_url || null,
      };
  }
}

/** ¿Vale la pena seguir consultando el resultado? */
export function debeSeguirConsultando(r: DevPrResultDTO | null): boolean {
  if (!r) return true;
  return !r.terminal;
}
