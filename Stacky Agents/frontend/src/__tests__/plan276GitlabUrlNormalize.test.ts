/**
 * Plan 276 F8.3 — `normalizeGitlabUrl` tiene que dejar SOLO el origen.
 *
 * El gotcha histórico: el operador copia la URL del proyecto desde la barra del
 * navegador (`https://srvcgit01.imsolutions.local/ripley/agenda-web`) y la pega en
 * "URL base". Con la versión vieja (que solo sacaba la barra final y un `/api/v4`)
 * el namespace quedaba PEGADO a la base_url y todas las llamadas a la API salían
 * ruteadas a `.../ripley/agenda-web/api/v4/...` → HTTP 404. Este archivo es el gate
 * corrido CONTRA ese defecto: los casos "namespace pegado" y "con puerto" fallan
 * con la implementación anterior.
 *
 * RTL/jsdom NO están instalados en este repo, así que la lógica vive en un módulo
 * puro (`src/projects/newProjectGitlabModel.ts`) y acá se testea sin montar nada.
 */
import { describe, it, expect } from "vitest";
import { normalizeGitlabUrl } from "../projects/newProjectGitlabModel";

describe("plan 276 F8.3 — normalizeGitlabUrl deja solo el origen", () => {
  it("recorta el namespace pegado (el defecto que este plan mata)", () => {
    expect(normalizeGitlabUrl("https://srvcgit01.imsolutions.local/ripley/agenda-web")).toBe(
      "https://srvcgit01.imsolutions.local"
    );
  });

  it("saca el /api/v4 del final", () => {
    expect(normalizeGitlabUrl("https://gl.io/api/v4")).toBe("https://gl.io");
  });

  it("saca la barra final", () => {
    expect(normalizeGitlabUrl("https://gitlab.com/")).toBe("https://gitlab.com");
  });

  it("una URL ya limpia queda idéntica", () => {
    expect(normalizeGitlabUrl("https://gitlab.com")).toBe("https://gitlab.com");
  });

  it("conserva el puerto y recorta el path", () => {
    expect(normalizeGitlabUrl("https://srvcgit01.imsolutions.local:8443/grupo/proyecto")).toBe(
      "https://srvcgit01.imsolutions.local:8443"
    );
  });

  it("el string vacío queda vacío (no revienta ni inventa un origen)", () => {
    expect(normalizeGitlabUrl("")).toBe("");
  });
});
