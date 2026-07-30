import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Plan 273 F2 (B-05) + F3 (B-07) — la nav v1 no deja tabs inalcanzables y se lee
 * en los dos temas, sin literales de color.
 *
 * Test PURO de archivos: RTL/jsdom NO estan instalados (SS3.2). La formula WCAG se
 * implementa aca; no hay DOM ni getComputedStyle.
 */

const SRC = resolve(__dirname, "..");
const APP_CSS = readFileSync(resolve(SRC, "App.module.css"), "utf8");
const THEME_CSS = readFileSync(resolve(SRC, "theme.css"), "utf8");

/** Extrae el CUERPO de una regla CSS por su selector exacto. */
function ruleBody(css: string, selector: string): string | null {
  // Selector literal + `{` ... hasta el primer `}` en columna 0 o `\n}`.
  const i = css.indexOf(`${selector} {`);
  if (i < 0) return null;
  const j = css.indexOf("\n}", i);
  if (j < 0) return null;
  return css.slice(i + selector.length + 2, j);
}

/** Bloque de tokens de theme.css (mismo regex no-greedy que themeContrast.test.ts). */
function tokenBlock(re: RegExp): Record<string, string> {
  const m = THEME_CSS.match(re);
  const out: Record<string, string> = {};
  if (!m) return out;
  for (const line of m[1].split(";")) {
    const t = line.match(/(--[\w-]+)\s*:\s*([^;]+)/);
    if (t) out[t[1]] = t[2].trim();
  }
  return out;
}
const BASE = tokenBlock(/:root\s*\{([\s\S]*?)\n\}/);
const LIGHT = tokenBlock(/:root\[data-theme="light"\]\s*\{([\s\S]*?)\n\}/);

// ── WCAG: luminancia relativa y ratio de contraste ────────────────────────────
/**
 * Devuelve [r,g,b,a]. El ALPHA no es un detalle: `rgba(255,255,255,0.45)` sobre
 * --bg-panel oscuro da 4.48:1 (falla AA por 0.02), pero si se ignora el alpha se
 * lo lee como blanco puro y da ~15:1, o sea el gate NO ve el defecto del tema
 * oscuro que este plan documenta. Sin compositing este test sub-detecta.
 */
function parseColor(v: string): [number, number, number, number] | null {
  const hex = v.match(/^#([0-9a-fA-F]{3,8})$/);
  if (hex) {
    let h = hex[1];
    if (h.length === 3) h = h.split("").map((c) => c + c).join("");
    const a = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
    return [
      parseInt(h.slice(0, 2), 16),
      parseInt(h.slice(2, 4), 16),
      parseInt(h.slice(4, 6), 16),
      a,
    ];
  }
  const rgba = v.match(/rgba?\(([^)]+)\)/);
  if (rgba) {
    const p = rgba[1].split(",").map((x) => parseFloat(x.trim()));
    if (p.length >= 3) return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  }
  return null;
}
/** Composita src (con alpha) sobre dst (opaco), como lo hace el navegador. */
function composite(
  src: [number, number, number, number],
  dst: [number, number, number, number]
): [number, number, number, number] {
  const a = src[3];
  if (a >= 1) return src;
  return [
    src[0] * a + dst[0] * (1 - a),
    src[1] * a + dst[1] * (1 - a),
    src[2] * a + dst[2] * (1 - a),
    1,
  ];
}
function luminance([r, g, b]: [number, number, number, number]): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
function ratio(fg: string, bg: string): number {
  const rawFg = parseColor(fg);
  const b = parseColor(bg);
  if (!rawFg || !b) return 0;
  const a = composite(rawFg, b);
  const l1 = luminance(a);
  const l2 = luminance(b);
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}
/** Resuelve `var(--x)` contra un bloque de tokens; devuelve el literal si ya lo es. */
function resolveToken(value: string, block: Record<string, string>): string {
  const v = value.trim();
  const m = v.match(/^var\((--[\w-]+)\)$/);
  if (!m) return v;
  const raw = block[m[1]];
  return raw ? resolveToken(raw, block) : "";
}
/** Lee una propiedad del cuerpo de una regla. */
function prop(body: string | null, name: string): string | null {
  if (!body) return null;
  const m = body.match(new RegExp(`(?:^|;|\\n)\\s*${name}\\s*:\\s*([^;\\n]+)`));
  return m ? m[1].trim() : null;
}

describe("plan273 F2 — la nav v1 no deja tabs inalcanzables (B-05)", () => {
  it("la_regla_nav_tiene_mecanismo_de_recuperacion_ante_desborde", () => {
    const body = ruleBody(APP_CSS, ".nav");
    expect(body, "no se encontro la regla .nav en App.module.css").toBeTruthy();
    // OJO: se afirma sobre el BLOQUE de .nav, NO sobre el archivo entero.
    // .shellContent ya tiene `overflow: auto` y un grep de archivo completo
    // pasaria EN FALSO (riesgo R10 del plan).
    const hasRecovery = /overflow-x/.test(body!) || /flex-wrap/.test(body!);
    expect(
      hasRecovery,
      "la regla .nav no declara overflow-x ni flex-wrap: con las 18 secciones " +
        "habilitadas los ultimos tabs quedan FUERA del viewport (los items son " +
        "white-space: nowrap y el contenedor no envuelve ni scrollea)"
    ).toBe(true);
  });
});

describe("plan273 F3 — la nav v1 se lee en los dos temas (B-07)", () => {
  it("cero_rgba_de_blanco_en_las_reglas_de_la_nav", () => {
    const hits = APP_CSS.split("\n")
      .map((l, i) => [i + 1, l] as const)
      .filter(([, l]) => l.includes("rgba(255, 255, 255"));
    expect(
      hits.map(([n, l]) => `App.module.css:${n}: ${l.trim()}`),
      "un rgba de blanco no lo puede re-apuntar el tema: es invisible en tema claro"
    ).toEqual([]);
  });

  it("cero_hex_en_App_module_css", () => {
    // Contenido CRUDO, sin strip de comentarios — igual que uiDebtRatchet.test.ts:21+58.
    // C13: PROHIBIDO documentar un color en un comentario de este archivo.
    const hits = APP_CSS.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [];
    expect(
      hits,
      `App.module.css tiene ${hits.length} literales hex: ${hits.join(", ")}. ` +
        `Si son comentarios, reescribirlos SIN el literal (C13): el gate cuenta ` +
        `contenido crudo. No relajar el gate ni regenerar el baseline.`
    ).toEqual([]);
  });

  it("el_texto_de_tab_cumple_AA_en_los_dos_temas", () => {
    const color = prop(ruleBody(APP_CSS, ".navTab"), "color");
    expect(color, ".navTab no declara color").toBeTruthy();
    const fails: string[] = [];
    for (const [name, block] of [["oscuro", BASE], ["claro", LIGHT]] as const) {
      const fg = resolveToken(color!, block);
      const bg = resolveToken("var(--bg-panel)", block);
      const r = ratio(fg, bg);
      if (r < 4.5) fails.push(`${name}: ${fg} sobre ${bg} = ${r.toFixed(2)}:1 (< 4.5)`);
    }
    expect(fails, `el texto de tab en reposo falla AA:\n${fails.join("\n")}`).toEqual([]);
  });

  it("el_badge_no_usa_status_danger_solid", () => {
    // Tripwire contra la recomendacion literal de la auditoria (SS3.7b): en oscuro
    // --status-danger-solid vale #ef4444 y blanco encima da 3.76:1, una falla AA
    // ya congelada en themeContrast.test.ts. PASA desde el principio: hoy el badge
    // usa un literal. Es preventivo, no un gate contra el defecto actual.
    const body = ruleBody(APP_CSS, ".navBadge");
    expect(body, "no se encontro la regla .navBadge").toBeTruthy();
    expect(
      /--status-danger-solid/.test(body!),
      "el badge NO debe tokenizarse con --status-danger-solid: bajaria el contraste " +
        "de 6.47:1 a 3.76:1 en tema oscuro (falla AA ya documentada)"
    ).toBe(false);
  });

  it("el_fondo_del_badge_cumple_AA_con_su_texto_en_los_dos_temas", () => {
    const body = ruleBody(APP_CSS, ".navBadge");
    const bgProp = prop(body, "background");
    const fgProp = prop(body, "color");
    expect(bgProp, ".navBadge no declara background").toBeTruthy();
    expect(fgProp, ".navBadge no declara color").toBeTruthy();
    const fails: string[] = [];
    for (const [name, block] of [["oscuro", BASE], ["claro", LIGHT]] as const) {
      // --text-on-solid es INVARIANTE a proposito (themeContrast INVARIANT):
      // no se re-apunta en claro, asi que se resuelve contra el bloque base.
      const fg = resolveToken(fgProp!, block) || resolveToken(fgProp!, BASE);
      const bg = resolveToken(bgProp!, block);
      const r = ratio(fg, bg);
      if (r < 4.5) fails.push(`${name}: ${fg} sobre ${bg} = ${r.toFixed(2)}:1 (< 4.5)`);
    }
    expect(fails, `el badge falla AA:\n${fails.join("\n")}`).toEqual([]);
  });
});
