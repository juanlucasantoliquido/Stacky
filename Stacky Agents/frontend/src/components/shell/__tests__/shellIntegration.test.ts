import { describe, it, expect } from "vitest";
import * as fs from "fs";

const APP = fs.readFileSync(new URL("../../../App.tsx", import.meta.url), "utf-8");

describe("Plan 139 F5 — integración shell v2 en App.tsx (guard byte-identidad OFF)", () => {
  it("conserva la <nav> v1 verbatim (rama OFF byte-idéntica, KPI-1)", () => {
    expect(APP).toContain('<nav className={styles.nav}>');
  });
  it("wirea el sidebar v2 y el modelo puro (rama ON)", () => {
    expect(APP).toContain("<AppSidebar");
    expect(APP).toContain("computeVisibleTabs");
    expect(APP).toContain("shellV2Enabled");
  });
  it("extrae el fragment `pages` con sus condicionales de montaje (§3.7, cero remount)", () => {
    expect(APP).toContain("const pages = (");
    expect(APP).toContain('tab === "team"');
    expect(APP).toContain('tab === "dbcompare"');
  });
});
