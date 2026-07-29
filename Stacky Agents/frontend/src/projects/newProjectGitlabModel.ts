/** Plan 259 F5 — lógica pura del alta GitLab. Sin React y sin red:
 *  RTL/jsdom no están instalados en este repo, así que TODO lo testeable vive acá
 *  y el `.tsx` solo pinta. */

import type { GitlabEngineResult } from "../types";

export interface GitlabFormValues {
  gitlab_url?: string;
  gitlab_project?: string;
  gitlab_token?: string;
  gitlab_group?: string;
  gitlab_enable_engine?: boolean;
}

/** Errores por campo del bloque GitLab. {} = válido. */
export function validateGitlabFields(f: GitlabFormValues): Record<string, string> {
  const errs: Record<string, string> = {};
  const url = (f.gitlab_url ?? "").trim();
  const proj = (f.gitlab_project ?? "").trim();
  if (!url) errs.gitlab_url = "Ingresá la URL base de GitLab (ej: https://gitlab.com)";
  else if (!/^https?:\/\//i.test(url)) errs.gitlab_url = "La URL tiene que empezar con http:// o https://";
  else if (/\/api\/v4\/?$/i.test(url)) errs.gitlab_url = "Quitá el /api/v4 del final: lo agrega Stacky";
  if (!proj) errs.gitlab_project = "Ingresá el path del proyecto (ej: grupo/proyecto)";
  else if (/^https?:\/\//i.test(proj)) errs.gitlab_project = "Poné solo el path, sin https:// ni el dominio";
  if (!(f.gitlab_token ?? "").trim()) errs.gitlab_token = "Pegá el token de acceso de GitLab";
  return errs;
}

/** Quita la barra final y un /api/v4 pegado; no toca nada más. */
export function normalizeGitlabUrl(raw: string): string {
  return (raw ?? "").trim().replace(/\/+$/, "").replace(/\/api\/v4$/i, "");
}

/** 'https://gitlab.com/acme/api/-/issues' → 'acme/api'. Un path ya limpio queda igual. */
export function normalizeGitlabProjectPath(raw: string): string {
  let v = (raw ?? "").trim();
  v = v.replace(/^https?:\/\/[^/]+\//i, "");
  v = v.split("/-/")[0];
  return v.replace(/^\/+/, "").replace(/\/+$/, "");
}

/** Default del motor: tildado salvo que el operador lo haya destildado. */
export function engineCheckboxDefault(current: boolean | undefined): boolean {
  return current === undefined ? true : current;
}

/** Orden DOM del bloque GitLab, para el foco-al-primer-error (patrón NP_FIELD_DOM_ORDER). */
export const GITLAB_FIELD_DOM_ORDER = ["gitlab_url", "gitlab_project", "gitlab_token"] as const;

/** ¿Se pinta el botón 🦊 GitLab en el selector de tracker?
 *  Fail-open: una flag ausente (health caído, servidor viejo) se comporta como
 *  encendida. El servidor igual valida, así que mostrar de más nunca corrompe. */
export function showGitlabTrackerButton(f: { onboardingGitlab?: boolean }): boolean {
  return f.onboardingGitlab !== false;
}

/** ¿Se pinta el botón ℹ️ INFO? En este plan SOLO GitLab tiene guía: nada de un
 *  INFO que abre un panel vacío. */
export function showInfoButton(trackerType: string, f: { setupGuide?: boolean }): boolean {
  return trackerType === "gitlab" && f.setupGuide !== false;
}

export interface EngineNotice {
  level: "none" | "info" | "warn";
  text: string;
}

/** Qué se le dice al operador sobre el motor tras crear el proyecto.
 *
 *  `handleSubmit` cierra el modal en el camino feliz (`onCreated(); onClose();`),
 *  así que un mensaje pintado adentro sería invisible: solo el nivel "warn"
 *  justifica NO cerrar (v2, hallazgo C9). */
export function engineNoticeFor(r: GitlabEngineResult | undefined): EngineNotice {
  if (!r) return { level: "none", text: "" };
  if (r.error) {
    return {
      level: "warn",
      text:
        "El proyecto se creó, pero no se pudo activar el motor GitLab. " +
        "Activalo en Configuración → Paridad de proveedores.",
    };
  }
  if (r.skipped) return { level: "none", text: "" };
  if (r.changed) return { level: "info", text: "Motor GitLab activado." };
  if (r.already_on) return { level: "info", text: "El motor GitLab ya estaba activado." };
  return { level: "none", text: "" };
}

/** Saca el mensaje humano de un Error de api.* ("400 BAD REQUEST: {json}").
 *  Devuelve el texto crudo si no hay JSON parseable.
 *
 *  Necesario porque `api.post` LANZA en cualquier non-2xx (api/client.ts), así
 *  que la rama `result.ok === false` de handleSubmit es inalcanzable y el
 *  operador leería el JSON crudo del rechazo (v3, hallazgo B11). */
export function humanizeApiError(raw: string): string {
  const i = raw.indexOf("{");
  if (i < 0) return raw;
  try {
    const body = JSON.parse(raw.slice(i));
    return String(body.error || body.message || raw);
  } catch {
    return raw;
  }
}
