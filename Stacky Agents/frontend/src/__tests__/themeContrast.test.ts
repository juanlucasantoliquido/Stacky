import { describe, it, expect } from "vitest";
import * as fs from "fs";

const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

function block(selector: RegExp): Record<string, string> {
  const m = THEME.match(selector);
  const body = m ? m[1] : "";
  const map: Record<string, string> = {};
  for (const line of body.split(";")) {
    const mm = line.match(/(--[a-z0-9-]+)\s*:\s*(.+)$/i);
    if (mm) map[mm[1]] = mm[2].trim();
  }
  return map;
}
const BASE = block(/:root\s*\{([\s\S]*?)\n\}/);                       // dark (base)
const LIGHT = block(/:root\[data-theme="light"\]\s*\{([\s\S]*?)\n\}/); // light

function toRgba(v: string): [number, number, number, number] {
  const s = v.trim();
  if (s.startsWith("#")) {
    let h = s.slice(1);
    if (h.length === 3) h = h.split("").map((c) => c + c).join("");
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1];
  }
  const m = s.match(/rgba?\(([^)]+)\)/)!;
  const p = m[1].split(",").map((x) => parseFloat(x.trim()));
  return [p[0], p[1], p[2], p[3] ?? 1];
}
function resolveColor(token: string, theme: Record<string, string>): [number, number, number, number] {
  const raw = theme[token] ?? BASE[token];
  const varRef = raw.match(/^var\((--[a-z0-9-]+)\)$/i);
  if (varRef) return resolveColor(varRef[1], theme);
  return toRgba(raw);
}
function lin(c: number) { const x = c / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }
function lum([r, g, b]: number[]) { return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); }
function composite(fg: number[], base: number[]) {
  const a = fg[3];
  return [0, 1, 2].map((i) => Math.round(fg[i] * a + base[i] * (1 - a)));
}
function ratio(fgTok: string, bgTok: string, theme: Record<string, string>): number {
  const base = resolveColor("--bg-base", theme).slice(0, 3);
  const fg = resolveColor(fgTok, theme).slice(0, 3);
  const bgc = resolveColor(bgTok, theme);
  const bg = bgc[3] >= 1 ? bgc.slice(0, 3) : composite(bgc, base);
  const L1 = lum(fg), L2 = lum(bg);
  return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
}

// Lista CONGELADA de pares (fg, bg). Ver plan 141 § 6.
const PAIRS: Array<[string, string]> = [
  ["--text-primary", "--bg-base"], ["--text-primary", "--bg-panel"], ["--text-primary", "--bg-elev"],
  ["--text-muted", "--bg-base"], ["--text-muted", "--bg-panel"],
  ["--accent", "--bg-base"], ["--accent-hot", "--bg-base"],
  ["--success", "--bg-base"], ["--warn", "--bg-base"], ["--danger", "--bg-base"],
  ["--agent-business", "--bg-base"], ["--agent-functional", "--bg-base"], ["--agent-technical", "--bg-base"],
  ["--agent-developer", "--bg-base"], ["--agent-qa", "--bg-base"],
  ["--status-success-text", "--status-success-bg"], ["--status-warning-text", "--status-warning-bg"],
  ["--status-danger-text", "--status-danger-bg"], ["--status-info-text", "--status-info-bg"],
  ["--status-neutral-text", "--status-neutral-bg"],
  ["--text-on-solid", "--status-success-solid"], ["--text-on-warn", "--status-warning-solid"],
  ["--text-on-solid", "--status-danger-solid"], ["--text-on-solid", "--status-info-solid"],
];
const AA = 4.5;

// Excepciones DARK conocidas y documentadas (§ 6): texto blanco sobre solids brillantes
// del 138. El dark es byte-idéntico ⇒ NO se "arreglan". Se pinnea el ratio como tripwire.
const DARK_SHORTFALLS: Record<string, number> = {
  "--text-on-solid|--status-success-solid": 2.28,
  "--text-on-solid|--status-danger-solid": 3.76,
  "--text-on-solid|--status-info-solid": 3.68,
};

describe("Plan 141 F3 — gate WCAG AA modo CLARO (estricto)", () => {
  it("los 24 pares cumplen AA (>= 4.5) en el tema claro", () => {
    const fails = PAIRS
      .map(([f, b]) => [f, b, ratio(f, b, LIGHT)] as const)
      .filter(([, , r]) => r < AA);
    expect(fails.map(([f, b, r]) => `${f}/${b}=${r.toFixed(2)}`)).toEqual([]);
  });
});

describe("Plan 141 F3 — gate WCAG AA modo OSCURO (con excepciones frozen)", () => {
  it("todo par cumple AA salvo las 3 excepciones documentadas", () => {
    const unexpected = PAIRS
      .map(([f, b]) => [`${f}|${b}`, ratio(f, b, BASE)] as const)
      .filter(([key, r]) => r < AA && !(key in DARK_SHORTFALLS));
    expect(unexpected.map(([k, r]) => `${k}=${r.toFixed(2)}`)).toEqual([]);
  });
  it("las excepciones dark siguen en su ratio documentado (tripwire anti-drift)", () => {
    for (const [key, expected] of Object.entries(DARK_SHORTFALLS)) {
      const [f, b] = key.split("|");
      expect(Math.abs(ratio(f, b, BASE) - expected)).toBeLessThan(0.1);
    }
  });
});

// [ADICIÓN ARQUITECTO v2] — anti-drift de color base↔claro (gate mecánico del contrato §12).
describe("Plan 141 F3 — anti-drift de color base ↔ tema claro", () => {
  it("todo token con valor de color del :root base está re-apuntado en claro (salvo invariantes de texto-sobre-solid)", () => {
    const isColor = (v: string) => /#[0-9a-fA-F]|rgba?\(/.test(v);
    // Invariantes a propósito: texto que va SIEMPRE del mismo color sobre solids (§6).
    // --status-neutral-text se auto-themea (var(--text-muted)) ⇒ isColor=false ⇒ excluido.
    const INVARIANT = new Set(["--text-on-solid", "--text-on-warn"]);
    const drift = Object.keys(BASE)
      .filter((k) => isColor(BASE[k]) && !INVARIANT.has(k) && !(k in LIGHT))
      .sort();
    // ESTE gate es la FUENTE DE VERDAD de completitud del bloque claro (C3). Si `drift` NO
    // está vacío, reconciliá en el MISMO commit: (1) agregá cada token al bloque
    // :root[data-theme="light"] de theme.css; (2) agregalo a REQUIRED de
    // themeLightTokens.test.ts; (3) BUMPEÁ el literal `.toBe(N)` de esa misma suite (F2) al
    // nuevo conteo. Sólo va a INVARIANT si es texto invariante sobre un solid. Esto impide
    // que un plan futuro introduzca un color dark-only sin decisión consciente.
    expect(drift, `Tokens de color sin re-apuntar en claro: ${drift.join(", ")}`).toEqual([]);
  });
});
