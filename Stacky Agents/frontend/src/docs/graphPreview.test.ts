/**
 * graphPreview.test.ts — Plan 268 F6.1. Tests PUROS del extracto del markdown.
 */
import { describe, it, expect } from "vitest";
import { previewExcerpt, previewTitle } from "./graphPreview";

describe("previewExcerpt (plan 268 F6.1)", () => {
  it("previewExcerpt con undefined devuelve cadena vacia", () => {
    expect(previewExcerpt(undefined)).toBe("");
  });

  it("previewExcerpt con cadena vacia devuelve cadena vacia", () => {
    expect(previewExcerpt("")).toBe("");
  });

  it("previewExcerpt quita el frontmatter YAML inicial", () => {
    const md = "---\ntitulo: Hola\ntags: [a, b]\n---\nCuerpo real.";
    expect(previewExcerpt(md)).toBe("Cuerpo real.");
  });

  it("previewExcerpt con frontmatter sin cierre NO borra el documento", () => {
    const md = "---\ntitulo: Hola\nCuerpo que igual hay que mostrar.";
    const out = previewExcerpt(md);
    expect(out).toContain("Cuerpo que igual hay que mostrar.");
  });

  it("previewExcerpt quita los bloques de codigo cercados", () => {
    const md = "Antes.\n\n```py\nprint('secreto')\n```\n\nDespues.";
    const out = previewExcerpt(md);
    expect(out).toContain("Antes.");
    expect(out).toContain("Despues.");
    expect(out).not.toContain("print");
  });

  it("previewExcerpt con un cercado sin cierre no borra el resto", () => {
    const md = "Antes.\n\n```py\nprint('x')";
    expect(previewExcerpt(md)).toContain("Antes.");
  });

  it("previewExcerpt quita las almohadillas de los encabezados", () => {
    expect(previewExcerpt("# Titulo\n## Sub\nTexto.")).toBe("Titulo Sub Texto.");
  });

  it("previewExcerpt quita citas y vinetas", () => {
    expect(previewExcerpt("> una cita\n- uno\n* dos\n+ tres")).toBe("una cita uno dos tres");
  });

  it("previewExcerpt convierte un link markdown en su texto", () => {
    expect(previewExcerpt("Ver [la guia](https://x.y/z) ahora.")).toBe("Ver la guia ahora.");
  });

  it("previewExcerpt convierte un wikilink con alias en el alias", () => {
    expect(previewExcerpt("Ver [[nota-larga|la nota]] ya.")).toBe("Ver la nota ya.");
  });

  it("previewExcerpt convierte un wikilink sin alias en el nombre", () => {
    expect(previewExcerpt("Ver [[mi-nota]] ya.")).toBe("Ver mi-nota ya.");
  });

  it("previewExcerpt colapsa saltos de linea en un solo espacio", () => {
    expect(previewExcerpt("uno\n\n\ndos\t\ttres")).toBe("uno dos tres");
  });

  it("previewExcerpt corta en maxChars y agrega puntos suspensivos", () => {
    const md = "palabra ".repeat(200);
    const out = previewExcerpt(md, 50);
    expect(out.endsWith("…")).toBe(true);
    expect(out.length).toBeLessThanOrEqual(51);
  });

  it("previewExcerpt no agrega puntos suspensivos si el texto entra entero", () => {
    expect(previewExcerpt("corto", 600)).toBe("corto");
  });

  it("previewExcerpt corta en el ultimo espacio, no a mitad de palabra", () => {
    const out = previewExcerpt("aaa bbb ccc ddd", 9);
    expect(out).toBe("aaa bbb…");
  });

  it("previewExcerpt con un documento de una sola palabra no agrega puntos", () => {
    expect(previewExcerpt("palabra")).toBe("palabra");
  });

  it("previewExcerpt de solo frontmatter devuelve cadena vacia", () => {
    expect(previewExcerpt("---\na: 1\n---\n")).toBe("");
  });

  it("previewExcerpt conserva el guion bajo de un nombre con snake_case", () => {
    // Se quitan * y backticks; el guion bajo SOLO se quita duplicado (__negrita__),
    // para no destrozar nombres de archivo ni de simbolo en la vista previa.
    expect(previewExcerpt("El modulo doc_indexer usa **fuerza** y `codigo`.")).toBe(
      "El modulo doc_indexer usa fuerza y codigo."
    );
    expect(previewExcerpt("texto __marcado__ aca")).toBe("texto marcado aca");
  });

  it("previewExcerpt sobre 100 KB termina en menos de 1000 ms", () => {
    const md = "Lorem ipsum dolor sit amet [link](http://a.b) [[nota|alias]] ".repeat(1800);
    expect(md.length).toBeGreaterThan(100000);
    const t0 = Date.now();
    const out = previewExcerpt(md, 600);
    const dt = Date.now() - t0;
    expect(out.length).toBeLessThanOrEqual(601);
    expect(dt).toBeLessThan(1000);
  });
});

describe("previewTitle (plan 268 F6.1)", () => {
  it("previewTitle devuelve el primer H1 sin la almohadilla", () => {
    expect(previewTitle("# Mi titulo\n\nTexto")).toBe("Mi titulo");
  });

  it("previewTitle ignora un H1 que este dentro del frontmatter", () => {
    expect(previewTitle("---\nnota: '# no soy titulo'\n---\n# Titulo real")).toBe("Titulo real");
  });

  it("previewTitle devuelve null si no hay H1", () => {
    expect(previewTitle("## Solo sub\nTexto")).toBeNull();
    expect(previewTitle("")).toBeNull();
    expect(previewTitle(undefined)).toBeNull();
  });
});
