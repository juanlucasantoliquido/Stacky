/**
 * Plan 276 F7 — los rótulos de la pantalla de tickets siguen al tracker del
 * proyecto activo, no dicen "ADO" siempre.
 *
 * RTL/jsdom NO están instalados en este repo, así que la lógica vive en un módulo
 * puro (`src/lib/trackerLabels.ts`). El último caso (v2/C5) es el gate del literal
 * `TicketBoard.tsx` "Sincronizá con ADO": como no se puede montar el componente,
 * se verifica sobre el TEXTO FUENTE del archivo de producción — de lo contrario el
 * caso sería autocumplido (compondría el mensaje con la misma función que testea y
 * pasaría igual con el literal viejo intacto en la pantalla).
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, it, expect } from "vitest";
import { accionSincronizar, nombreDeTracker, tituloDeTickets } from "../lib/trackerLabels";

const TICKET_BOARD = readFileSync(
  fileURLToPath(new URL("../pages/TicketBoard.tsx", import.meta.url)),
  "utf8",
);

describe("plan 276 F7 — nombreDeTracker", () => {
  it("resuelve los 4 tipos conocidos", () => {
    expect(nombreDeTracker("azure_devops")).toBe("ADO");
    expect(nombreDeTracker("gitlab")).toBe("GitLab");
    expect(nombreDeTracker("jira")).toBe("Jira");
    expect(nombreDeTracker("mantis")).toBe("Mantis");
  });

  it("un tipo desconocido cae a Tracker, NUNCA a ADO", () => {
    expect(nombreDeTracker("bitbucket")).toBe("Tracker");
    expect(nombreDeTracker("")).toBe("Tracker");
  });

  it("undefined y null caen a Tracker (proyecto sin cargar todavía)", () => {
    expect(nombreDeTracker(undefined)).toBe("Tracker");
    expect(nombreDeTracker(null)).toBe("Tracker");
  });
});

describe("plan 276 F7 — rótulos compuestos", () => {
  it("tituloDeTickets sigue al tracker y conserva el texto de hoy para ADO", () => {
    expect(tituloDeTickets("gitlab")).toBe("Tickets GitLab");
    expect(tituloDeTickets("azure_devops")).toBe("Tickets ADO");
  });

  it("accionSincronizar conserva el texto de hoy para ADO (backward-compat)", () => {
    expect(accionSincronizar("azure_devops")).toBe("Sincronizar ADO");
    expect(accionSincronizar("gitlab")).toBe("Sincronizar GitLab");
  });

  it("v2/C5 — el estado vacío del board no dice ADO en un proyecto GitLab", () => {
    // Propiedad del rótulo compuesto…
    const mensaje = `No hay tickets para este proyecto. Sincronizá con ${nombreDeTracker(
      "gitlab",
    )} para traerlos.`;
    expect(mensaje).toContain("GitLab");
    expect(mensaje).not.toContain("ADO");
    // …y gate CONTRA el defecto: el literal hardcodeado ya no está en producción y
    // el mensaje se compone con la función. Sin estas dos asserts el caso de arriba
    // pasa con `TicketBoard.tsx` intacto.
    expect(TICKET_BOARD).not.toContain("Sincronizá con ADO");
    expect(TICKET_BOARD).toContain("Sincronizá con ${nombreDeTracker(");
  });
});
