/**
 * Plan 143 F6 — el plan 143 CONSUME el reduced-motion del 141, no lo redefine; y sus
 * utilidades no animan propiedades de layout (§4.4).
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";

const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

describe("Plan 143 F6 — deslinde con 141 (reduced-motion)", () => {
  it("conserva EXACTAMENTE 1 bloque prefers-reduced-motion (el del plan 141 F5)", () => {
    const n = (THEME.match(/@media \(prefers-reduced-motion: reduce\)/g) || []).length;
    expect(n).toBe(1);
  });
});

describe("Plan 143 F6 — utilidades presentes, sin reflow y con contrato óptimista", () => {
  const BLOCK = THEME.slice(THEME.indexOf("/* ─── Micro-interacciones tokenizadas (Plan 143)"));

  it("existen las utilidades tokenizadas", () => {
    for (const cls of [".u-pressable", ".u-pending", ".u-fade-in", ".u-fade-in-up", ".u-transition-colors"]) {
      expect(THEME, `Falta la utilidad ${cls}`).toContain(cls);
    }
  });

  // [ADICIÓN ARQUITECTO] guard ROBUSTO (C6): detecta CUALQUIER propiedad de layout animada, en
  // shorthand o longhand y en cualquier posición del valor — no solo "transition: width". Cubre
  // "transition: opacity, width 0.2s" y "transition-property: height", que el guard v1 se salteaba.
  const LAYOUT = "width|height|top|left|right|bottom|inset|margin|padding|inline-size|block-size";
  it("ninguna utilidad anima propiedades de layout (§4.4)", () => {
    const re = new RegExp(`transition(?:-property)?\\s*:[^;{}]*\\b(?:${LAYOUT})\\b`, "g");
    const offenders = BLOCK.match(re) || [];
    expect(offenders, `Utilidad anima layout (reflow): ${offenders.join(" | ")}`).toEqual([]);
    // Los @keyframes del bloque 143 solo pueden animar opacity/transform (sin layout).
    const kfs = BLOCK.match(/@keyframes[\s\S]*?\}\s*\}/g) || [];
    for (const kf of kfs) {
      const bad = kf.match(new RegExp(`\\b(?:${LAYOUT})\\s*:`, "g"));
      expect(bad, `keyframe anima layout: ${kf.slice(0, 48)}`).toBeNull();
    }
  });

  // [ADICIÓN ARQUITECTO] contrato VISUAL del feedback óptimista (C4/C5): .u-pending DEBE atenuar
  // (opacity < 1) Y bloquear (pointer-events: none). Así el "en vuelo" es inequívoco y quitar la
  // clase revierte el estado: blinda la reversión-ante-fallo que el hook garantiza en su `finally`.
  it(".u-pending atenúa y bloquea (contrato de feedback óptimista)", () => {
    const m = BLOCK.match(/\.u-pending\s*\{[^}]*\}/);
    expect(m, "Falta el bloque .u-pending").not.toBeNull();
    const body = m ? m[0] : "";
    expect(/opacity\s*:\s*0?\.\d+/.test(body), ".u-pending debe atenuar (opacity < 1)").toBe(true);
    expect(/pointer-events\s*:\s*none/.test(body), ".u-pending debe bloquear la interacción").toBe(true);
  });
});
