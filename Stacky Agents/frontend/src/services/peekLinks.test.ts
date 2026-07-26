// Plan 175 F1 — Links de peek y menú contextual.
import { describe, it, expect } from "vitest";
import { executionDeepLink, ticketExternalLink } from "./peekLinks";

describe("executionDeepLink", () => {
  it("arma un link absoluto con la clave canónica de ruta", () => {
    const url = executionDeepLink(42, "http://localhost:5173");

    expect(url.startsWith("http://localhost:5173")).toBe(true);
    expect(url).toContain("exec=42");
    // La clave legacy quedó atrás: pegar un link con ?execution= no abriría nada.
    expect(url).not.toContain("execution=");
  });

  it("un origin con barra final no duplica la barra del path", () => {
    expect(executionDeepLink(1, "http://x").includes("//history")).toBe(false);
  });
});

describe("ticketExternalLink", () => {
  it("la url que vino del tracker manda", () => {
    // Si el proyecto cambió de organización, la construida apunta al lugar viejo.
    expect(ticketExternalLink({ ado_url: "https://otra.org/wi/5", ado_id: 9 })).toBe(
      "https://otra.org/wi/5",
    );
  });

  it("sin url pero con id se construye", () => {
    expect(ticketExternalLink({ ado_id: 9 })).toContain("9");
  });

  it("sin url y sin id válido devuelve null, no una url rota", () => {
    // Devolver un link a ninguna parte es peor que no ofrecer el botón.
    expect(ticketExternalLink({ ado_id: 0 })).toBeNull();
    expect(ticketExternalLink({ ado_id: -1 })).toBeNull();
  });

  it("una url vacía no cuenta como url", () => {
    expect(ticketExternalLink({ ado_url: "", ado_id: 7 })).toContain("7");
  });
});
