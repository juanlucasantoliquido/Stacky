/**
 * graphPreview.ts — Plan 268 F6.
 * Extracto legible del principio de un markdown, para el peek del grafo.
 * PURO: recibe el texto ya bajado, no hace fetch.
 *
 * El frontmatter y los bloques cercados se recortan con `indexOf`/`slice`, NO con un
 * regex greedy multilínea: un documento de 100 KB tiene que salir en milisegundos y
 * sin riesgo de retroceso catastrófico.
 */

/** Quita el frontmatter YAML inicial. Si el bloque NO cierra, devuelve el texto
 *  tal cual (borrar todo el documento por un `---` suelto sería peor que no filtrar). */
function stripFrontmatter(md: string): string {
  if (!md.startsWith("---")) return md;
  const firstNl = md.indexOf("\n");
  if (firstNl < 0) return md;
  if (md.slice(3, firstNl).trim() !== "") return md; // "--- algo" no es frontmatter
  const close = md.indexOf("\n---", firstNl);
  if (close < 0) return md; // sin cierre: NO se borra el documento
  const eol = md.indexOf("\n", close + 1);
  return eol < 0 ? "" : md.slice(eol + 1);
}

/** Quita los bloques de código CERCADOS COMPLETOS. Un cercado sin cierre se deja. */
function stripFences(md: string): string {
  let out = "";
  let i = 0;
  for (;;) {
    const open = md.indexOf("```", i);
    if (open < 0) {
      out += md.slice(i);
      break;
    }
    const close = md.indexOf("```", open + 3);
    if (close < 0) {
      out += md.slice(i); // cercado sin cierre: se conserva el resto
      break;
    }
    out += md.slice(i, open) + " ";
    i = close + 3;
  }
  return out;
}

/** Aplana las marcas de markdown a texto llano. */
function stripMarks(md: string): string {
  return (
    md
      // wikilinks primero: [[nombre|alias]] → alias ; [[nombre]] → nombre
      .replace(/\[\[([^\]|]*)(?:\|([^\]]*))?\]\]/g, (_m, name, alias) => (alias ? alias : name))
      // links markdown: [texto](url) → texto. Con paréntesis anidados en la url se
      // queda el texto del corchete y sobra un ")": aceptable y documentado.
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
      // reglas horizontales
      .replace(/^[ \t]{0,3}(-{3,}|\*{3,}|_{3,})[ \t]*$/gm, " ")
      // encabezados, citas y viñetas (marca de línea)
      .replace(/^[ \t]{0,3}#{1,6}[ \t]+/gm, "")
      .replace(/^[ \t]{0,3}>+[ \t]?/gm, "")
      .replace(/^[ \t]{0,3}[-*+][ \t]+/gm, "")
      // énfasis e inline code. El guion bajo se quita SOLO duplicado, para no
      // destrozar snake_case en nombres de archivo o de símbolo.
      .replace(/__/g, "")
      .replace(/[*`]/g, "")
  );
}

/**
 * Devuelve hasta `maxChars` caracteres de texto plano:
 *  1. quita el frontmatter YAML inicial
 *  2. quita los bloques de código cercados completos
 *  3. quita marcas de encabezado, énfasis, citas y viñetas
 *  4. convierte [texto](url) → texto y [[nombre|alias]] → alias (o nombre)
 *  5. colapsa runs de espacios/saltos a un solo espacio y hace trim
 *  6. corta en el último espacio antes de maxChars y agrega "…" si cortó
 * Entrada vacía/undefined → "". Texto más corto que maxChars → sin "…".
 */
export function previewExcerpt(markdown: string | undefined, maxChars: number = 600): string {
  if (!markdown) return "";
  const text = stripMarks(stripFences(stripFrontmatter(markdown)))
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return "";
  const limit = Math.max(0, maxChars);
  if (text.length <= limit) return text;
  const slice = text.slice(0, limit);
  const lastSpace = slice.lastIndexOf(" ");
  return (lastSpace > 0 ? slice.slice(0, lastSpace) : slice) + "…";
}

/** Primer encabezado H1 del markdown (sin el #), o null. Ignora el frontmatter. */
export function previewTitle(markdown: string | undefined): string | null {
  if (!markdown) return null;
  const body = stripFrontmatter(markdown);
  const m = /^[ \t]{0,3}#[ \t]+(.+)$/m.exec(body);
  return m ? m[1].trim() : null;
}
