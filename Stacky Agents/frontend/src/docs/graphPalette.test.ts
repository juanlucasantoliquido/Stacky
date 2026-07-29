/**
 * graphPalette.test.ts — Plan 268 F0.6.
 * Guardia contra el bug VIVO del plan 111: el canvas del grafo leía tokens
 * `--color-*` que NO existen en el tema, así que dibujaba SIEMPRE los hex de
 * fallback y nunca acompañaba el tema. Este test lee `src/theme.css` de disco
 * (igual que los ratchets: sin DOM, sin jsdom) y falla si un token del grafo no
 * está definido en el bloque OSCURO y en el CLARO.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";
import {
  GRAPH_PALETTE_TOKENS,
  GROUP_SLOT_TOKENS,
  allGraphTokenNames,
  definedTokenNames,
  splitThemeBlocks,
} from "./graphPalette";

const FRONTEND_ROOT = process.cwd(); // correr SIEMPRE desde Stacky Agents/frontend
const SRC = path.join(FRONTEND_ROOT, "src");
const THEME_PATH = path.join(SRC, "theme.css");

function readTheme(): string {
  return fs.readFileSync(THEME_PATH, "utf-8");
}

/** Alcance CERRADO (B7): SOLO los archivos que el plan 268 posee. Ampliarlo trae
 *  32 hits de deuda ajena (DocBacklinksPanel, DocCoveragePanel, DocumenterResultPanel)
 *  que este plan no puede tocar, y dejaría el test rojo para siempre. */
const OWNED_FILES = [
  "components/docs/DocGraphView.module.css",
  "components/docs/DocGraphExplorer.module.css",
  "components/docs/DocGraphView.tsx",
];

/** Quita comentarios de bloque. SIN esto el gate se auto-caza: los comentarios de
 *  DocGraphExplorer.module.css y de DocGraphView.tsx documentan la regla nombrando
 *  `var(--duration-*)` y `var(--token)`, que no son tokens reales — y un gate que
 *  nunca puede dar verde se ignora a los dos días. Validado en las dos direcciones:
 *  con el filtro el barrido da 0 y sigue dando ROJO ante un token inexistente de
 *  verdad (ver el caso "detecta un token inexistente en una declaracion real"). */
function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/^[ \t]*\/\/.*$/gm, " ");
}

/** Nombres de token USADOS vía `var(--x)` (ignora el 2.º argumento de fallback). */
function usedTokenNames(css: string): Set<string> {
  const out = new Set<string>();
  const re = /var\(\s*(--[a-zA-Z0-9-]+)/g;
  let m: RegExpExecArray | null;
  const code = stripComments(css);
  while ((m = re.exec(code)) !== null) out.add(m[1]);
  return out;
}

describe("graphPalette (plan 268 F0.6)", () => {
  it("todos los tokens del grafo estan definidos en el bloque OSCURO de theme.css", () => {
    const { dark } = splitThemeBlocks(readTheme());
    const defined = definedTokenNames(dark);
    const missing = allGraphTokenNames().filter((t) => !defined.has(t));
    expect(missing, `tokens ausentes del bloque oscuro: ${missing.join(", ")}`).toEqual([]);
  });

  it("todos los tokens del grafo estan definidos en el bloque CLARO de theme.css", () => {
    const { light } = splitThemeBlocks(readTheme());
    expect(light.length, "el bloque del tema claro no se encontro en theme.css").toBeGreaterThan(0);
    const defined = definedTokenNames(light);
    const missing = allGraphTokenNames().filter((t) => !defined.has(t));
    expect(missing, `tokens ausentes del bloque claro: ${missing.join(", ")}`).toEqual([]);
  });

  it("ningun token del grafo empieza con --color- (esa familia no existe en el tema)", () => {
    const bad = allGraphTokenNames().filter((t) => t.startsWith("--color-"));
    expect(bad).toEqual([]);
  });

  it("los 6 slots de grupo son tokens DISTINTOS entre si", () => {
    const names = GROUP_SLOT_TOKENS.map((g) => g.token);
    expect(names.length).toBe(6);
    expect(new Set(names).size).toBe(6);
  });

  it("cada entrada de GRAPH_PALETTE_TOKENS trae token y fallback no vacios", () => {
    for (const [role, entry] of Object.entries(GRAPH_PALETTE_TOKENS)) {
      expect(entry.token.startsWith("--"), `${role} sin token`).toBe(true);
      expect(entry.fallback.length, `${role} sin fallback`).toBeGreaterThan(0);
    }
  });

  it("definedTokenNames encuentra una custom property y ignora un var() de uso", () => {
    const defined = definedTokenNames(":root { --propia: #fff; color: var(--ajena); }");
    expect(defined.has("--propia")).toBe(true);
    expect(defined.has("--ajena")).toBe(false);
  });

  it("splitThemeBlocks separa el bloque claro por data-theme=light", () => {
    const css = ':root { --a: 1; }\n:root[data-theme="light"] { --a: 2; }\n';
    const { dark, light } = splitThemeBlocks(css);
    expect(dark).toContain("--a: 1");
    expect(dark).not.toContain("--a: 2");
    expect(light).toContain("--a: 2");
  });

  it("splitThemeBlocks sin bloque claro devuelve light vacio", () => {
    const { dark, light } = splitThemeBlocks(":root { --a: 1; }");
    expect(dark).toContain("--a: 1");
    expect(light).toBe("");
  });

  it("detecta un token inexistente en una declaracion real (el gate NO es decorativo)", () => {
    // El gate se corre CONTRA el defecto: si esto no fuera rojo, el barrido de abajo
    // no mediria nada. El token falso es de la familia --color-*, que es exactamente
    // el bug vivo del plan 111 que F0.6 arregla.
    const defined = definedTokenNames(readTheme());
    // El literal va PARTIDO a proposito, y esta prosa evita nombrarlo de una pieza:
    // el grep manual de DoD-11 exige CERO usos de la familia de tokens inexistente en
    // los archivos del plan, y tanto el fixture como un comentario que lo citara
    // literal serian hits — el gate se volveria insatisfacible por culpa de su propio
    // test (gotcha conocido de la casa: la prosa choca con su propio gate).
    const FAKE = "--color-" + "inexistente-a-proposito";
    const bad = usedTokenNames(`.x { color: var(${FAKE}); }`);
    expect(bad.has(FAKE)).toBe(true);
    expect(defined.has(FAKE)).toBe(false);
    // ...y un token nombrado SOLO en un comentario no cuenta (si contara, el gate
    // quedaria rojo para siempre y se ignoraria).
    expect(usedTokenNames("/* usar var(--token) del tema */ .x { color: var(--accent); }")).toEqual(
      new Set(["--accent"])
    );
  });

  it("DocGraphView.module.css no usa ningun token inexistente", () => {
    const defined = definedTokenNames(readTheme());
    const errors: string[] = [];
    for (const rel of OWNED_FILES) {
      const abs = path.join(SRC, rel);
      if (!fs.existsSync(abs)) continue; // DocGraphExplorer.module.css nace en F1
      const used = usedTokenNames(fs.readFileSync(abs, "utf-8"));
      for (const token of used) {
        if (!defined.has(token)) errors.push(`${rel}: var(${token}) no esta definido en theme.css`);
      }
    }
    expect(errors, errors.join("\n")).toEqual([]);
  });
});
