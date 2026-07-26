/**
 * Plan 201 F0/F10 — la sección "Compilar" está registrada y gateada por su flag.
 *
 * RTL/jsdom no están instalados en este repo, así que el render del componente NO
 * es automatizable: el gate real es `tsc --noEmit` + smoke manual. Lo que sí se
 * verifica acá es el registro declarativo, que es donde se rompen las secciones.
 */
import { describe, expect, it } from "vitest";

import { DEVOPS_SECTIONS } from "../DevOpsPage";

describe("sección Compilar (Plan 201)", () => {
  it("está registrada con su flag y health key", () => {
    const seccion = DEVOPS_SECTIONS.find((s) => s.id === "taller-compilacion");

    expect(seccion).toBeDefined();
    expect(seccion?.gateFlagKey).toBe("STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED");
    expect(seccion?.healthKey).toBe("build_workshop_enabled");
    expect(seccion?.label).toBe("Compilar");
    expect(typeof seccion?.render).toBe("function");
  });

  it("no duplica el id de otra sección", () => {
    const ids = DEVOPS_SECTIONS.map((s) => s.id);

    expect(new Set(ids).size).toBe(ids.length);
  });

  it("toda sección con healthKey declara su flag y su mensaje", () => {
    for (const s of DEVOPS_SECTIONS) {
      if (s.healthKey) {
        expect(s.gateFlagKey, `${s.id} sin gateFlagKey`).toBeTruthy();
        expect(s.gateMessage, `${s.id} sin gateMessage`).toBeTruthy();
      }
    }
  });
});
