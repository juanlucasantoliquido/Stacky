import { describe, it, expect } from "vitest";
import * as fs from "fs";

const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

/** Extrae el cuerpo del bloque :root[data-theme="light"] { ... }. */
function lightBlock(): string {
  const m = THEME.match(/:root\[data-theme="light"\]\s*\{([\s\S]*?)\}/);
  return m ? m[1] : "";
}
const LIGHT = lightBlock();

// Tokens de COLOR que el bloque claro DEBE re-apuntar (nombre → valor exacto).
const REQUIRED: Array<[string, string]> = [
  ["--bg-base", "#ffffff"],
  ["--bg-panel", "#f6f8fa"],
  ["--bg-elev", "#eaeef2"],
  ["--border", "#d0d7de"],
  ["--border-muted", "#eaeef2"],
  ["--mono-bg", "#f6f8fa"],
  ["--text-primary", "#1f2328"],
  ["--text-muted", "#57606a"],
  ["--text-faint", "#6e7781"],
  ["--accent", "#0969da"],
  ["--accent-hot", "#0550ae"],
  ["--success", "#1a7f37"],
  ["--warn", "#9a6700"],
  ["--danger", "#cf222e"],
  ["--agent-business", "#8250df"],
  ["--agent-functional", "#bc4c00"],
  ["--agent-technical", "#0969da"],
  ["--agent-developer", "#1a7f37"],
  ["--agent-qa", "#9a6700"],
  ["--agent-custom", "#57606a"],
  ["--card-shadow", "0 2px 12px rgba(140, 149, 159, 0.15)"],
  ["--status-success-text", "#116329"],
  ["--status-success-soft-text", "#166534"],
  ["--status-success-solid", "#1a7f37"],
  ["--status-success-bg", "rgba(34, 197, 94, 0.14)"],
  ["--status-success-border", "rgba(34, 197, 94, 0.35)"],
  ["--status-warning-text", "#7d4e00"],
  ["--status-warning-soft-text", "#8a5a00"],
  ["--status-warning-muted-text", "#7d4e00"],
  ["--status-warning-solid", "#bf8700"],
  ["--status-warning-bg", "rgba(245, 158, 11, 0.16)"],
  ["--status-warning-border", "rgba(245, 158, 11, 0.4)"],
  ["--status-danger-text", "#b31c28"],
  ["--status-danger-soft-text", "#cf222e"],
  ["--status-danger-solid", "#cf222e"],
  ["--status-danger-bg", "rgba(239, 68, 68, 0.13)"],
  ["--status-danger-border", "rgba(239, 68, 68, 0.35)"],
  ["--status-info-text", "#0a58ca"],
  ["--status-info-solid", "#0969da"],
  ["--status-info-hot", "#0550ae"],
  ["--status-info-bg", "rgba(59, 130, 246, 0.12)"],
  ["--status-info-border", "rgba(59, 130, 246, 0.4)"],
  ["--status-neutral-bg", "rgba(31, 35, 40, 0.06)"],
  ["--status-neutral-border", "rgba(31, 35, 40, 0.15)"],
  ["--accent-active", "#0550ae"],
  ["--warn-hover", "#7d5300"],
  ["--focus-ring", "0 0 0 3px rgba(9, 105, 218, 0.35)"],
  ["--spinner-track", "rgba(31, 35, 40, 0.15)"],
  ["--shadow-1", "0 1px 3px rgba(31, 35, 40, 0.12)"],
  ["--shadow-2", "0 2px 12px rgba(31, 35, 40, 0.14)"],
  ["--shadow-3", "0 8px 24px rgba(31, 35, 40, 0.18)"],
  ["--shadow-overlay", "0 16px 48px rgba(31, 35, 40, 0.24)"],
  ["--color-scheme", "light"],
];

// Tokens INVARIANTES al tema: PROHIBIDO que aparezcan en el bloque claro.
const FORBIDDEN = [
  "--space-1", "--space-9",
  "--text-2xs", "--text-sm", "--text-2xl",
  "--weight-regular", "--weight-bold",
  "--leading-tight", "--leading-relaxed",
  "--radius-xs", "--radius-md", "--radius-lg", "--radius-full",
  "--duration-fast", "--duration-slow",
  "--ease-standard", "--ease-out-expo",
  "--border-width",
];

describe("Plan 141 F2 — bloque claro completo y correcto", () => {
  it("existe el bloque :root[data-theme=\"light\"]", () => {
    expect(LIGHT.length).toBeGreaterThan(0);
  });
  it("re-apunta los 53 tokens de color con valor exacto", () => {
    const missing = REQUIRED.filter(([n, v]) => !LIGHT.includes(`${n}: ${v};`));
    expect(missing.map(([n]) => n)).toEqual([]);
    // CONTEO ACOPLADO (C3): 52 tokens de color no-invariantes del :root base del 138
    // (contrato §10.1) + `--color-scheme` = 53. La FUENTE DE VERDAD de completitud es el
    // anti-drift de F3 (themeContrast.test.ts), que deriva el censo del base mecánicamente.
    // Este `.toBe(53)` es un tripwire SECUNDARIO: si F3 obliga a agregar/quitar un token de
    // color en el base, actualizá REQUIRED y BUMPEÁ este literal EN EL MISMO commit.
    expect(REQUIRED.length).toBe(53);
  });
  it("NO duplica tokens invariantes al tema (spacing/tipografía/radio/motion/border-width)", () => {
    const leaked = FORBIDDEN.filter((n) => LIGHT.includes(`${n}:`));
    expect(leaked).toEqual([]);
  });
  it("NO re-declara --status-neutral-text (auto-tema vía var(--text-muted))", () => {
    expect(LIGHT.includes("--status-neutral-text:")).toBe(false);
  });
});
