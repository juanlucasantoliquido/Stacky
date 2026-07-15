import { describe, it, expect } from "vitest";
import { ICON_BY_NAME } from "../shellIcons";
import { TAB_META } from "../shellNav";

describe("shellIcons — cobertura de iconografía", () => {
  it("todo iconName de TAB_META existe en ICON_BY_NAME", () => {
    for (const t of Object.keys(TAB_META) as (keyof typeof TAB_META)[]) {
      const name = TAB_META[t].iconName;
      expect(ICON_BY_NAME[name], `falta icono para ${name}`).toBeTruthy();
    }
  });

  it("cada entrada de ICON_BY_NAME es un componente (objeto o función)", () => {
    for (const name of Object.keys(ICON_BY_NAME)) {
      expect(["object", "function"]).toContain(typeof ICON_BY_NAME[name]);
    }
  });
});
