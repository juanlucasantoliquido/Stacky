/**
 * graphPalette.ts — Plan 268 F0.6.
 * ÚNICA fuente de verdad de los tokens de color que el grafo documental lee del
 * tema. PURO: solo nombres y fallbacks, sin DOM. El test lee theme.css de disco y
 * verifica que cada token esté definido en el bloque oscuro Y en el claro.
 *
 * REGLA: acá NO se inventan tokens. Todo nombre de esta lista tiene que existir
 * ya en frontend/src/theme.css. Si hace falta un color nuevo, se elige otro token
 * existente; agregar tokens al tema es otro plan (contrato congelado del 138,
 * vigilado por src/__tests__/themeTokens.test.ts).
 */

/** Rol semántico dentro del grafo → token del tema + fallback (por si el tema no cargó aún). */
export const GRAPH_PALETTE_TOKENS = {
  note: { token: "--accent", fallback: "#388bfd" },
  code: { token: "--success", fallback: "#3fb950" },
  missing: { token: "--danger", fallback: "#f85149" },
  edge: { token: "--border", fallback: "#30363d" },
  stale: { token: "--danger", fallback: "#f85149" },
  label: { token: "--text-primary", fallback: "#e6edf3" },
  labelBg: { token: "--bg-panel", fallback: "#161b22" },
  halo: { token: "--accent-hot", fallback: "#58a6ff" },
  ring: { token: "--text-primary", fallback: "#e6edf3" },
} as const;

/** Colores por SLOT de grupo (F5). Orden fijo = orden de asignación de slots.
 *  Los 6 existen en el bloque oscuro y en el claro de theme.css. */
export const GROUP_SLOT_TOKENS = [
  { token: "--accent", fallback: "#388bfd" }, // slot 0
  { token: "--accent-hot", fallback: "#58a6ff" }, // slot 1
  { token: "--warn", fallback: "#d29922" }, // slot 2
  { token: "--agent-business", fallback: "#a371f7" }, // slot 3
  { token: "--agent-functional", fallback: "#f78166" }, // slot 4
  { token: "--agent-custom", fallback: "#8b949e" }, // slot 5
] as const;

/** Todos los nombres de token usados por el grafo (para el test de existencia). */
export function allGraphTokenNames(): string[] {
  const a = Object.values(GRAPH_PALETTE_TOKENS).map((e) => e.token);
  const b = GROUP_SLOT_TOKENS.map((e) => e.token);
  return Array.from(new Set([...a, ...b])).sort();
}

/** Parseo PURO de un CSS: nombres de custom properties DEFINIDAS (`--x: valor;`). */
export function definedTokenNames(css: string): Set<string> {
  const out = new Set<string>();
  const re = /(--[a-zA-Z0-9-]+)\s*:/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(css)) !== null) out.add(m[1]);
  return out;
}

/**
 * Corta el CSS del tema en sus dos bloques: el `:root` base (oscuro) y el bloque
 * del tema claro. Devuelve `{ dark, light }` con el TEXTO de cada uno.
 * Criterio: el bloque claro arranca en el selector que contiene `data-theme="light"`.
 * Si no se encuentra ese selector, `light` queda vacio (y el test correspondiente
 * falla, que es el comportamiento deseado: significa que el tema claro se rompio).
 */
export function splitThemeBlocks(css: string): { dark: string; light: string } {
  const marker = css.indexOf('[data-theme="light"]');
  if (marker < 0) return { dark: css, light: "" };
  const open = css.indexOf("{", marker);
  const close = css.indexOf("}", open);
  return {
    dark: css.slice(0, marker),
    light: open < 0 || close < 0 ? "" : css.slice(open + 1, close),
  };
}
