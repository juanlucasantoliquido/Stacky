// Plan 282 F5 — el link deja de apuntar al tracker de OTRO cliente.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { urlDeTicket, adoUrl } from "../trackerUrls";

const FUENTE = readFileSync(join(__dirname, "..", "trackerUrls.ts"), "utf-8");

describe("Plan 282 F5 — urlDeTicket", () => {
  it("1 — ticket GitLab con URL del backend: se usa TAL CUAL", () => {
    const u = urlDeTicket(
      { type: "gitlab", ado_url: "https://gitlab.interno/grupo/proy/-/issues/1115" },
      1115,
    );
    expect(u).toBe("https://gitlab.interno/grupo/proy/-/issues/1115");
  });

  it("2 — ticket GitLab SIN URL del backend: null, NUNCA dev.azure.com", () => {
    const u = urlDeTicket({ type: "gitlab" }, 1115);
    expect(u).toBeNull();
  });

  it("3 — ticket ADO con org+proyecto: usa ESA org, no una hardcodeada", () => {
    const u = urlDeTicket(
      { type: "azure_devops", organization: "MiOrg", project: "MiProyecto" },
      1234,
    );
    expect(u).toBe("https://dev.azure.com/MiOrg/MiProyecto/_workitems/edit/1234");
  });

  it("4 — ticket ADO sin organización configurada: null", () => {
    expect(urlDeTicket({ type: "azure_devops" }, 1234)).toBeNull();
    expect(urlDeTicket({ type: "azure_devops", organization: "MiOrg" }, 1234)).toBeNull();
    expect(adoUrl("1234")).toBeNull();
  });

  it("5 — guarda anti-regresión: la org de otro cliente ya no está en el fuente", () => {
    // El detector detecta PRIMERO sobre un sintético que SÍ la tiene: un assert
    // de ausencia que nunca vio un positivo no prueba nada.
    const sintetico = "return `https://dev.azure.com/Ubimia" + "Pacifico/x`;";
    expect(sintetico).toContain("Ubimia" + "Pacifico");
    expect(FUENTE).not.toContain("Ubimia" + "Pacifico");
    expect(FUENTE).not.toContain("Strategist_" + "Pacifico");
  });
});
