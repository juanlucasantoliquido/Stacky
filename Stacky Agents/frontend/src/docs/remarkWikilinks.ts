/**
 * remarkWikilinks.ts — Plan 111 F0.
 *
 * Remark plugin PURO que transforma `[[nombre]]` / `[[nombre|alias]]` que aparecen
 * dentro de nodos `text` del mdast en nodos `link` con una URL marcadora
 * `wikilink:<nombre>`. NO toca código, links normales ni bloques de código
 * (inlineCode/code no se recorren porque su contenido vive en `.value`, no como
 * children de tipo text). Determinístico. Nunca lanza.
 *
 * Los tipos vienen transitivamente de react-markdown@9 (mdast/unified); NO se agrega
 * ninguna dependencia a package.json. El plugin opera sobre el árbol que
 * react-markdown le pasa en runtime.
 */
import type { Root, Text, Link, PhrasingContent } from "mdast";
import type { Plugin } from "unified";

const WIKILINK_RE = /\[\[([^\]|\n]+?)(?:\|([^\]\n]*))?\]\]/g;

/**
 * remarkWikilinks — transforma [[nombre]] y [[nombre|alias]] en nodos link con
 * url "wikilink:<nombre-trim>". El texto visible es el alias si existe, si no el nombre.
 */
export const remarkWikilinks: Plugin<[], Root> = () => (tree: Root) => {
  visitTextNodes(tree, (node, index, parent) => {
    const value = node.value;
    if (!value.includes("[[")) return; // fast path
    const parts: PhrasingContent[] = [];
    let last = 0;
    WIKILINK_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = WIKILINK_RE.exec(value)) !== null) {
      const name = m[1].trim();
      if (!name) continue; // [[]] o [[   ]] → se ignora, queda como texto
      if (m.index > last) {
        parts.push({ type: "text", value: value.slice(last, m.index) } as Text);
      }
      const label = (m[2] ?? "").trim() || name;
      const link: Link = {
        type: "link",
        url: "wikilink:" + name,
        children: [{ type: "text", value: label } as Text],
      };
      parts.push(link);
      last = m.index + m[0].length;
    }
    if (parts.length === 0) return; // no hubo match real
    if (last < value.length) {
      parts.push({ type: "text", value: value.slice(last) } as Text);
    }
    parent.children.splice(index, 1, ...parts); // reemplaza el text node
    return index + parts.length; // continuar después de lo insertado
  });
};

type ParentNode = { type: string; children?: unknown[]; [k: string]: unknown };
/** Parent garantizado con children (el visitor solo llama cb en este caso). */
type TextParent = { type: string; children: unknown[]; [k: string]: unknown };

/**
 * visitTextNodes — recorrido propio (sin unist-util-visit para no depender de su API).
 * Recorre recursivo, saltea nodos type "code"/"inlineCode" (no tienen children de
 * texto), y llama al callback sobre nodos "text". Si el callback devuelve un número,
 * el recorrido continúa desde ese índice (después de los nodos insertados).
 */
function visitTextNodes(
  tree: Root,
  cb: (node: Text, index: number, parent: TextParent) => number | void
): void {
  walk(tree as unknown as ParentNode);

  function walk(node: ParentNode): void {
    if (!node || typeof node !== "object") return;
    if (node.type === "code" || node.type === "inlineCode") return;
    const children = node.children;
    if (!Array.isArray(children)) return;
    for (let i = 0; i < children.length; i++) {
      const child = children[i] as ParentNode | undefined;
      if (child && child.type === "text") {
        const res = cb(child as unknown as Text, i, node as TextParent);
        if (typeof res === "number") {
          i = res - 1; // saltear los nodos recién insertados
        }
      } else if (child) {
        walk(child);
      }
    }
  }
}
