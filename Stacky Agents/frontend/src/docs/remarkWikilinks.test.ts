import { describe, it, expect } from "vitest";
import type { Root } from "mdast";
import { remarkWikilinks } from "./remarkWikilinks";

/** Construye un Root mdast con un único párrafo que contiene un text node. */
function paragraphWithText(value: string): Root {
  return {
    type: "root",
    children: [
      {
        type: "paragraph",
        children: [{ type: "text", value }],
      },
    ],
  } as Root;
}

/** Aplica el plugin (mutación in-place) y devuelve los children del primer párrafo. */
function runOn(tree: Root): any[] {
  const transform = remarkWikilinks();
  transform(tree as any);
  return (tree.children[0] as any).children;
}

describe("remarkWikilinks", () => {
  it("transforms_simple_wikilink", () => {
    const tree = paragraphWithText("[[Nota Motor]]");
    const children = runOn(tree);
    expect(children).toHaveLength(1);
    expect(children[0]).toMatchObject({
      type: "link",
      url: "wikilink:Nota Motor",
      children: [{ type: "text", value: "Nota Motor" }],
    });
  });

  it("transforms_wikilink_with_alias", () => {
    const tree = paragraphWithText("[[Nota|el motor]]");
    const children = runOn(tree);
    expect(children).toHaveLength(1);
    expect(children[0]).toMatchObject({
      type: "link",
      url: "wikilink:Nota",
      children: [{ type: "text", value: "el motor" }],
    });
  });

  it("splits_mixed_text_and_wikilinks", () => {
    const tree = paragraphWithText("texto [[A]] medio [[B|b]] fin");
    const children = runOn(tree);
    expect(children.map((c: any) => c.type)).toEqual([
      "text",
      "link",
      "text",
      "link",
      "text",
    ]);
    expect(children[0]).toMatchObject({ type: "text", value: "texto " });
    expect(children[1]).toMatchObject({ type: "link", url: "wikilink:A" });
    expect(children[1].children[0]).toMatchObject({ value: "A" });
    expect(children[2]).toMatchObject({ type: "text", value: " medio " });
    expect(children[3]).toMatchObject({ type: "link", url: "wikilink:B" });
    expect(children[3].children[0]).toMatchObject({ value: "b" });
    expect(children[4]).toMatchObject({ type: "text", value: " fin" });
  });

  it("ignores_empty_wikilink", () => {
    const tree = paragraphWithText("antes [[]] y [[   ]] despues");
    const children = runOn(tree);
    // Sin match real → el text node queda intacto.
    expect(children).toHaveLength(1);
    expect(children[0]).toMatchObject({
      type: "text",
      value: "antes [[]] y [[   ]] despues",
    });
  });

  it("skips_inline_code", () => {
    const tree: Root = {
      type: "root",
      children: [
        {
          type: "paragraph",
          children: [
            { type: "inlineCode", value: "codigo [[X]]" } as any,
          ],
        },
      ],
    } as Root;
    const transform = remarkWikilinks();
    transform(tree as any);
    const children = (tree.children[0] as any).children;
    expect(children).toHaveLength(1);
    expect(children[0]).toMatchObject({
      type: "inlineCode",
      value: "codigo [[X]]",
    });
  });

  it("leaves_plain_text_untouched", () => {
    const tree = paragraphWithText("solo texto sin wikilinks");
    const children = runOn(tree);
    expect(children).toHaveLength(1);
    expect(children[0]).toMatchObject({
      type: "text",
      value: "solo texto sin wikilinks",
    });
  });
});
