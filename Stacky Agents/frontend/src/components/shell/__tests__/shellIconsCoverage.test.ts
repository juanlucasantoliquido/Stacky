// Plan 238 F7 [ADICION A1] — cobertura de iconos del shell.
// AppSidebar resuelve el icono por nombre en runtime: un iconName mal escrito
// devuelve undefined y rompe el render de TODA la barra lateral. Este test lo
// convierte en un rojo determinista, para este plan y para los tabs futuros.
import { describe, it, expect } from "vitest";
import { TAB_META } from "../shellNav";
import { ICON_BY_NAME } from "../shellIcons";

describe("shellIcons — cobertura de iconos", () => {
  it("todo iconName de TAB_META existe en ICON_BY_NAME", () => {
    const faltantes = Object.entries(TAB_META)
      .filter(([, meta]) => ICON_BY_NAME[meta.iconName] === undefined)
      .map(([tab, meta]) => `${tab} -> ${meta.iconName}`);
    expect(faltantes).toEqual([]);
  });
});
