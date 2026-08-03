// Plan 295 F5 — gate de las CUATRO patas de frontend del ca_bundle. Es un test de
// TEXTO FUENTE a proposito: lo que hay que garantizar es que el conducto esta
// soldado en los 4 archivos. Un test de render no lo probaria mejor (RTL/jsdom no
// estan instalados en este repo) y el punto no es como se ve sino que el dato viaje.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const leer = (p: string) => readFileSync(resolve(SRC, p), "utf-8");

describe("plan 295 F5 — el ca_bundle llega al verificador", () => {
  it("el tipo del payload de verifyGitlab lo declara", () => {
    const t = leer("api/endpoints.ts");
    // Se acota al BLOQUE de verifyGitlab en vez de grepear el archivo entero:
    // endpoints.ts es enorme y un toContain global podria pasar EN FALSO por una
    // mencion de gitlab_ca_bundle en cualquier otro endpoint.
    // El corte va hasta el rawPost que cierra la firma -- NO a una cantidad fija
    // de caracteres: un comentario nuevo en el tipo correria el campo fuera de la
    // ventana y el gate fallaria por su propio recorte, no por el codigo.
    const i = t.indexOf("verifyGitlab:");
    expect(i).toBeGreaterThan(-1);
    const fin = t.indexOf("rawPost", i);
    expect(fin).toBeGreaterThan(i);
    expect(t.slice(i, fin)).toContain("gitlab_ca_bundle");
  });

  it("el dialogo lo manda en runVerify", () => {
    const t = leer("components/SetupGuideDialog.tsx");
    expect(t).toContain("gitlab_ca_bundle: values.gitlab_ca_bundle");
  });

  it("los DOS modales lo pasan en values", () => {
    expect(leer("components/NewProjectModal.tsx")).toContain(
      "gitlab_ca_bundle: form.gitlab_ca_bundle",
    );
    expect(leer("components/EditProjectModal.tsx")).toContain(
      "gitlab_ca_bundle: String(form.gitlab_ca_bundle",
    );
  });
});
