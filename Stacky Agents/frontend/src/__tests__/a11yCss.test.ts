import { describe, it, expect } from "vitest";
import * as fs from "fs";

const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

describe("Plan 141 F5 — foco visible global", () => {
  it("hay una regla :focus-visible que usa el token --focus-ring", () => {
    expect(THEME).toContain(":focus-visible");
    expect(THEME).toContain("box-shadow: var(--focus-ring)");
  });
  it("el foco de inputs usa el token (no un rgba hardcodeado)", () => {
    // input:focus ahora usa var(--focus-ring); el rgba viejo desaparece.
    expect(THEME).toContain("box-shadow: var(--focus-ring)");
    expect(THEME).not.toContain("box-shadow: 0 0 0 3px rgba(56, 139, 253, 0.25)");
  });
});

describe("Plan 141 F5 — prefers-reduced-motion global", () => {
  it("neutraliza animaciones y transiciones (incluye spinners infinitos)", () => {
    expect(THEME).toContain("@media (prefers-reduced-motion: reduce)");
    expect(THEME).toContain("animation-iteration-count: 1 !important");
    expect(THEME).toContain("transition-duration: 0.01ms !important");
  });
});
