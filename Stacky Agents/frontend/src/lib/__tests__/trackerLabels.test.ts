// Plan 282 F4 — el diccionario de rótulos. Funciones puras: RTL/jsdom no están
// instalados en este repo, así que la lógica vive acá y los componentes pintan.
import { describe, it, expect } from "vitest";
import {
  refDeTicket,
  accionAbrirEn,
  accionPublicarComentario,
  etiquetaEstadoDestino,
  etiquetaEstadoDeTicket,
  sugerenciasDeEstadoFinal,
  labelDeTab,
  nombreDeTracker,
} from "../trackerLabels";

describe("Plan 282 F4 — trackerLabels", () => {
  it("1 — refDeTicket congela ADO PRIMERO", () => {
    expect(refDeTicket("azure_devops", 1234)).toBe("ADO-1234");
  });

  it("2 — refDeTicket usa la notación propia de GitLab", () => {
    expect(refDeTicket("gitlab", 1115)).toBe("#1115");
  });

  it("3 — sugerenciasDeEstadoFinal(gitlab) son las 4 claves lógicas REALES", () => {
    // Espejo de _state_map_for_gitlab (backend/services/gitlab_provider.py).
    // Sugerir "Done" en GitLab es la receta del transition_failed del plan 271.
    expect(sugerenciasDeEstadoFinal("gitlab")).toEqual([
      "functional", "accepted", "rejected", "in_progress",
    ]);
  });

  it("4 — sugerenciasDeEstadoFinal(ado) son las 4 <option> reales de hoy", () => {
    expect(sugerenciasDeEstadoFinal("azure_devops")).toEqual([
      "Done", "Closed", "Resolved", "Active",
    ]);
  });

  it("5 — tracker desconocido/null/undefined NUNCA devuelve ADO", () => {
    for (const t of ["bitbucket", "", null, undefined] as const) {
      expect(nombreDeTracker(t)).toBe("Tracker");
      expect(refDeTicket(t, 9)).not.toContain("ADO");
      expect(accionAbrirEn(t)).not.toContain("ADO");
      expect(accionPublicarComentario(t)).not.toContain("ADO");
      expect(etiquetaEstadoDestino(t)).not.toContain("ADO");
      expect(etiquetaEstadoDeTicket(t)).not.toContain("ADO");
      expect(sugerenciasDeEstadoFinal(t)).toEqual([]);
    }
  });

  it("6 — accionAbrirEn usa el nombre largo del tracker", () => {
    expect(accionAbrirEn("gitlab")).toBe("Abrir en GitLab ↗");
    expect(accionAbrirEn("azure_devops")).toBe("Abrir en Azure DevOps ↗");
    expect(accionAbrirEn(null)).toBe("Abrir en el tracker ↗");
  });

  it("7 — labelDeTab rutea el tab de tickets SIN tocar TAB_META", () => {
    expect(labelDeTab("tickets", "Tickets ADO", "gitlab")).toBe("Tickets GitLab");
    expect(labelDeTab("tickets", "Tickets ADO", "azure_devops")).toBe("Tickets ADO");
  });

  it("8 — labelDeTab devuelve el label estático de un tab que no es tickets", () => {
    // Sin este caso, un labelDeTab que reescribiera TODO pasaría igual el 7.
    expect(labelDeTab("devops", "DevOps", "gitlab")).toBe("DevOps");
    expect(labelDeTab("settings", "Configuración", "gitlab")).toBe("Configuración");
  });
});
