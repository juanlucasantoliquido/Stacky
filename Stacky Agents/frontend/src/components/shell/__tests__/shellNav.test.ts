import { describe, it, expect } from "vitest";
import {
  SHELL_NAV_GROUPS,
  TAB_META,
  computeVisibleTabs,
  orderedVisibleGroups,
  parseCollapsed,
  SIDEBAR_COLLAPSED_KEY,
} from "../shellNav";

const ALL_TABS = [
  "team", "tickets", "review", "unblocker", "pm", "logs", "settings",
  "docs", "memory", "diagnostics", "history", "migrador", "devops", "dbcompare",
  "costcenter", "planes",
] as const;

describe("shellNav — modelo de navegación", () => {
  it("TAB_META cubre exactamente los 16 tabs", () => {
    expect(Object.keys(TAB_META).sort()).toEqual([...ALL_TABS].sort());
  });

  it("cada tab aparece en exactamente un grupo (cobertura 16, sin duplicados)", () => {
    const flat = SHELL_NAV_GROUPS.flatMap((g) => g.tabs);
    expect(flat.slice().sort()).toEqual([...ALL_TABS].sort());
    expect(new Set(flat).size).toBe(flat.length);
  });

  it("orden de grupos congelado", () => {
    expect(SHELL_NAV_GROUPS.map((g) => g.id)).toEqual([
      "trabajo", "observabilidad", "conocimiento", "plataforma", "configuracion",
    ]);
  });

  it("todo tab tiene label no vacío e iconName", () => {
    for (const t of ALL_TABS) {
      expect(TAB_META[t].label.trim().length).toBeGreaterThan(0);
      expect(TAB_META[t].iconName.trim().length).toBeGreaterThan(0);
    }
  });

  it("computeVisibleTabs: los 6 base siempre visibles (team NO, es ocultable)", () => {
    const v = computeVisibleTabs({
      sections: { team: false, pm: false, logs: false, docs: false, memory: false },
      migradorEnabled: false, devopsEnabled: false, dbCompareEnabled: false,
      costCenterEnabled: false, planesEnabled: false,
    });
    expect([...v].sort()).toEqual(
      ["diagnostics", "history", "review", "settings", "tickets", "unblocker"].sort(),
    );
    // team NO aparece si su sección está oculta.
    expect(v.has("team")).toBe(false);
  });

  it("computeVisibleTabs: team aparece solo si su sección está visible", () => {
    const v = computeVisibleTabs({
      sections: { team: true, pm: false, logs: false, docs: false, memory: false },
      migradorEnabled: false, devopsEnabled: false, dbCompareEnabled: false,
      costCenterEnabled: false, planesEnabled: false,
    });
    expect(v.has("team")).toBe(true);
  });

  it("computeVisibleTabs: opcionales aparecen solo con su gate", () => {
    const v = computeVisibleTabs({
      sections: { team: true, pm: true, logs: true, docs: true, memory: true },
      migradorEnabled: true, devopsEnabled: true, dbCompareEnabled: true,
      costCenterEnabled: true, planesEnabled: true,
    });
    expect([...v].sort()).toEqual([...ALL_TABS].sort());
  });

  it("orderedVisibleGroups oculta grupos vacíos y filtra tabs ocultos", () => {
    const v = computeVisibleTabs({
      sections: { team: false, pm: false, logs: false, docs: false, memory: false },
      migradorEnabled: false, devopsEnabled: false, dbCompareEnabled: false,
      costCenterEnabled: false, planesEnabled: false,
    });
    const groups = orderedVisibleGroups(v);
    // conocimiento (docs/memory) y plataforma (devops/migrador/dbcompare) quedan vacíos
    expect(groups.map((g) => g.id)).toEqual(["trabajo", "observabilidad", "configuracion"]);
    const obs = groups.find((g) => g.id === "observabilidad")!;
    expect(obs.tabs.slice().sort()).toEqual(["diagnostics", "history"]);
    // "trabajo" ya no incluye team (oculto): solo tickets/review/unblocker.
    const trabajo = groups.find((g) => g.id === "trabajo")!;
    expect(trabajo.tabs.slice().sort()).toEqual(["review", "tickets", "unblocker"]);
  });

  it("parseCollapsed y clave de persistencia", () => {
    expect(SIDEBAR_COLLAPSED_KEY).toBe("stacky.ui.shell.collapsed");
    expect(parseCollapsed("true")).toBe(true);
    expect(parseCollapsed("false")).toBe(false);
    expect(parseCollapsed(null)).toBe(false);
    expect(parseCollapsed("garbage")).toBe(false);
  });
});
