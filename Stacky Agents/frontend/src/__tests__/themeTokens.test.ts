/**
 * Plan 138 F1 — Contrato de tokens del sistema de diseño v2.
 * Congela nombre y valor EXACTO de cada token nuevo, y verifica que los
 * tokens legacy no cambiaron. Fuente de verdad: plan 138 §10.1.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const THEME = fs.readFileSync(path.join(process.cwd(), "src", "theme.css"), "utf-8");
const FLAT = THEME.replace(/\s+/g, " ");

const FROZEN_TOKENS: Array<[string, string]> = [
  // §10.1.A Estados
  ["--status-success-text", "#4ade80"],
  ["--status-success-soft-text", "#86efac"],
  ["--status-success-solid", "#22c55e"],
  ["--status-success-bg", "rgba(34, 197, 94, 0.18)"],
  ["--status-success-border", "rgba(34, 197, 94, 0.3)"],
  ["--status-warning-text", "#fbbf24"],
  ["--status-warning-soft-text", "#fde68a"],
  ["--status-warning-muted-text", "#fdba74"],
  ["--status-warning-solid", "#f59e0b"],
  ["--status-warning-bg", "rgba(245, 158, 11, 0.18)"],
  ["--status-warning-border", "rgba(245, 158, 11, 0.28)"],
  ["--status-danger-text", "#f87171"],
  ["--status-danger-soft-text", "#fca5a5"],
  ["--status-danger-solid", "#ef4444"],
  ["--status-danger-bg", "rgba(239, 68, 68, 0.18)"],
  ["--status-danger-border", "rgba(239, 68, 68, 0.28)"],
  ["--status-info-text", "#93c5fd"],
  ["--status-info-solid", "#3b82f6"],
  ["--status-info-hot", "#60a5fa"],
  ["--status-info-bg", "rgba(59, 130, 246, 0.18)"],
  ["--status-info-border", "rgba(59, 130, 246, 0.4)"],
  ["--status-neutral-text", "var(--text-muted)"],
  ["--status-neutral-bg", "rgba(255, 255, 255, 0.06)"],
  ["--status-neutral-border", "rgba(255, 255, 255, 0.1)"],
  // §10.1.B Interacción
  ["--accent-active", "#1f6feb"],
  ["--warn-hover", "#e3b341"],
  ["--text-on-solid", "#ffffff"],
  ["--text-on-warn", "#1c1810"],
  ["--focus-ring", "0 0 0 3px rgba(56, 139, 253, 0.25)"],
  ["--spinner-track", "rgba(255, 255, 255, 0.15)"],
  // §10.1.C Spacing
  ["--space-1", "2px"],
  ["--space-2", "4px"],
  ["--space-3", "6px"],
  ["--space-4", "8px"],
  ["--space-5", "12px"],
  ["--space-6", "16px"],
  ["--space-7", "24px"],
  ["--space-8", "32px"],
  ["--space-9", "48px"],
  // §10.1.D Tipografía
  ["--text-2xs", "10px"],
  ["--text-xs", "11px"],
  ["--text-sm", "12px"],
  ["--text-md", "13px"],
  ["--text-lg", "15px"],
  ["--text-xl", "18px"],
  ["--text-2xl", "22px"],
  ["--weight-regular", "400"],
  ["--weight-medium", "500"],
  ["--weight-semibold", "600"],
  ["--weight-bold", "700"],
  ["--leading-tight", "1.2"],
  ["--leading-normal", "1.4"],
  ["--leading-relaxed", "1.6"],
  // §10.1.E Radios
  ["--radius-xs", "2px"],
  ["--radius-md", "6px"],
  ["--radius-lg", "10px"],
  ["--radius-full", "999px"],
  // §10.1.F Sombras
  ["--shadow-1", "0 1px 3px rgba(0, 0, 0, 0.3)"],
  ["--shadow-2", "0 2px 12px rgba(0, 0, 0, 0.35)"],
  ["--shadow-3", "0 8px 24px rgba(0, 0, 0, 0.45)"],
  ["--shadow-overlay", "0 16px 48px rgba(0, 0, 0, 0.55)"],
  // §10.1.G Motion
  ["--duration-fast", "0.12s"],
  ["--duration-base", "0.2s"],
  ["--duration-slow", "0.4s"],
  ["--ease-standard", "ease"],
  ["--ease-in-out", "ease-in-out"],
  ["--ease-out-expo", "cubic-bezier(0.16, 1, 0.3, 1)"],
  // §10.1.H Bordes / theme-ready
  ["--border-width", "1px"],
  ["--color-scheme", "dark"],
];

const LEGACY_TOKENS: Array<[string, string]> = [
  ["--bg-base", "#0d1117"],
  ["--bg-panel", "#161b22"],
  ["--bg-elev", "#21262d"],
  ["--border", "#30363d"],
  ["--text-primary", "#e6edf3"],
  ["--text-muted", "#8b949e"],
  ["--accent", "#388bfd"],
  ["--accent-hot", "#58a6ff"],
  ["--success", "#3fb950"],
  ["--warn", "#d29922"],
  ["--danger", "#f85149"],
  ["--radius", "6px"],
  ["--radius-sm", "4px"],
  ["--card-radius", "10px"],
  ["--card-shadow", "0 2px 12px rgba(0,0,0,0.35)"],
];

describe("themeTokens (plan 138 F1)", () => {
  it("tokens nuevos: 69 nombres con valor exacto", () => {
    expect(FROZEN_TOKENS.length).toBe(69);
    const missing = FROZEN_TOKENS.filter(([n, v]) => !FLAT.includes(`${n}: ${v};`));
    expect(missing, "Tokens faltantes o con valor distinto: " + missing.map(([n]) => n).join(", ")).toEqual([]);
  });

  it("tokens legacy intactos (R1 aditividad)", () => {
    const broken = LEGACY_TOKENS.filter(([n, v]) => !FLAT.includes(`${n}: ${v};`));
    expect(broken, "Tokens legacy alterados: " + broken.map(([n]) => n).join(", ")).toEqual([]);
  });

  it("theme-ready: color-scheme sale de la variable y aun NO hay data-theme (lo agrega el plan 141)", () => {
    expect(FLAT).toContain("color-scheme: var(--color-scheme)");
    expect(FLAT).toContain("THEME-READY");
    // El plan 141 elimina esta asercion cuando implemente el tema claro:
    expect(THEME.includes('[data-theme="light"]')).toBe(false);
  });
});
