/** Plan 259 F6 — lógica pura del panel de la guía de configuración.
 *  Sin React y sin red: RTL/jsdom no están instalados en este repo. */

export type CheckStatus = "ok" | "fail" | "unknown";

export interface GuideCheckResult {
  id: string;
  status: CheckStatus;
  message: string;
  detail?: string;
}

export interface GuideStepDoc {
  id: string;
  title: string;
  detail: string;
  where: string;
  trap?: string;
}

export interface GuideCheckDoc {
  id: string;
  title: string;
  fixes_step: string;
}

export interface SetupGuideDoc {
  provider: string;
  display_name: string;
  summary: string;
  required_fields: string[];
  steps: GuideStepDoc[];
  checks: GuideCheckDoc[];
}

/** Resumen para el encabezado del panel. */
export function summarizeChecks(
  rs: GuideCheckResult[]
): { ok: number; fail: number; unknown: number; verdict: CheckStatus } {
  const ok = rs.filter((r) => r.status === "ok").length;
  const fail = rs.filter((r) => r.status === "fail").length;
  const unknown = rs.filter((r) => r.status === "unknown").length;
  return { ok, fail, unknown, verdict: fail > 0 ? "fail" : unknown > 0 ? "unknown" : "ok" };
}

/** Ids de paso a resaltar: los que arreglan los chequeos en 'fail'.
 *  Devuelve en el orden de `guide.checks`, sin repetir. */
export function stepsToHighlight(
  guide: SetupGuideDoc | null,
  rs: GuideCheckResult[]
): string[] {
  if (!guide) return [];
  const failed = new Set(rs.filter((r) => r.status === "fail").map((r) => r.id));
  const out: string[] = [];
  for (const c of guide.checks) {
    if (failed.has(c.id) && !out.includes(c.fixes_step)) out.push(c.fixes_step);
  }
  return out;
}

/** El botón "Verificar ahora" se habilita solo con URL y path cargados. */
export function canVerify(v: { gitlab_url?: string; gitlab_project?: string }): boolean {
  return Boolean((v.gitlab_url ?? "").trim()) && Boolean((v.gitlab_project ?? "").trim());
}

/** Copia embebida mínima si el endpoint no responde. NUNCA deja al operador sin nada. */
export const GITLAB_FALLBACK_GUIDE: SetupGuideDoc = {
  provider: "gitlab",
  display_name: "GitLab",
  summary:
    "Stacky se conecta a GitLab por su API v4 con un token personal. Necesitás la URL " +
    "base de tu GitLab, el path del proyecto y un token con permiso de API.",
  required_fields: ["gitlab_url", "gitlab_project", "gitlab_token"],
  steps: [
    {
      id: "gl-01-instancia",
      title: "1. Identificá la URL base de tu GitLab",
      detail:
        "En la nube es https://gitlab.com ; si tu empresa tiene el suyo, es la raíz del " +
        "sitio. Va SIN barra al final y SIN /api/v4 : eso lo agrega Stacky.",
      where: "gitlab",
    },
    {
      id: "gl-02-token",
      title: "2. Creá un token de acceso con permiso 'api'",
      detail:
        "En GitLab: tu foto → 'Edit profile' → 'Access tokens' → 'Add new token'. Marcá " +
        "'api' (con 'read_api' Stacky no puede comentar ni cerrar). Copiá el token al " +
        "crearlo: GitLab no lo vuelve a mostrar.",
      where: "gitlab",
    },
    {
      id: "gl-04-project-path",
      title: "3. Anotá el path del proyecto",
      detail:
        "Es lo que viene después del dominio, sin https:// y sin la parte /-/algo. " +
        "Ejemplo: https://gitlab.com/acme/backend/api → acme/backend/api . También se " +
        "acepta el ID numérico del proyecto.",
      where: "gitlab",
    },
  ],
  checks: [],
};

/** true si la guía viene del servidor; false si es la copia embebida. */
export function isServerGuide(g: SetupGuideDoc | null): boolean {
  return Boolean(g) && g !== GITLAB_FALLBACK_GUIDE;
}
