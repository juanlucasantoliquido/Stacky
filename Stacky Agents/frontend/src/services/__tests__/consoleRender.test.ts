/**
 * consoleRender.test.ts — Plan 265 F2. 11 casos del doc.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/consoleRender.test.ts
 */
import { describe, it, expect } from "vitest";
import { groupLinesIntoChunks, isCommandChunk, stripAnsi } from "../consoleRender";
import type { LogLine } from "../../types";

function ln(message: string): LogLine {
  return { timestamp: "2026-07-29T00:00:00Z", level: "info", message };
}

describe("consoleRender", () => {
  it("1. líneas sin fences -> 1 chunk 'text'", () => {
    const chunks = groupLinesIntoChunks([ln("hola"), ln("mundo")]);
    expect(chunks.length).toBe(1);
    expect(chunks[0].kind).toBe("text");
  });

  it("2. fence ```bash cerrado -> 3 chunks: text, code(lang=bash), text", () => {
    const chunks = groupLinesIntoChunks([
      ln("antes"),
      ln("```bash"),
      ln("git status"),
      ln("```"),
      ln("despues"),
    ]);
    expect(chunks.map((c) => c.kind)).toEqual(["text", "code", "text"]);
    expect(chunks[1].lang).toBe("bash");
  });

  it("3. fence sin cerrar al final -> último chunk es 'code', no se traga el contenido", () => {
    const chunks = groupLinesIntoChunks([ln("antes"), ln("```"), ln("linea 1"), ln("linea 2")]);
    const last = chunks[chunks.length - 1];
    expect(last.kind).toBe("code");
    expect(last.content).toContain("linea 1");
    expect(last.content).toContain("linea 2");
  });

  it("4. [] -> [], no lanza", () => {
    expect(groupLinesIntoChunks([])).toEqual([]);
  });

  it("5. fence vacío -> chunk 'code' con content === ''", () => {
    const chunks = groupLinesIntoChunks([ln("```"), ln("```")]);
    expect(chunks.length).toBe(1);
    expect(chunks[0].kind).toBe("code");
    expect(chunks[0].content).toBe("");
  });

  it("6. isCommandChunk con lang: 'powershell' -> true", () => {
    expect(isCommandChunk({ kind: "code", lang: "powershell", content: "Get-Item .", copyable: true })).toBe(true);
  });

  it("7. isCommandChunk con content: 'git status', lang: null -> true", () => {
    expect(isCommandChunk({ kind: "code", lang: null, content: "git status", copyable: true })).toBe(true);
  });

  it("8. isCommandChunk con prosa de 3 líneas -> false", () => {
    const chunk = { kind: "code" as const, lang: null, content: "linea uno\nlinea dos\nlinea tres", copyable: true };
    expect(isCommandChunk(chunk)).toBe(false);
  });

  it("9. 5000 líneas termina en < 100 ms", () => {
    const lines = Array.from({ length: 5000 }, (_, i) => ln(`linea ${i}`));
    const start = performance.now();
    groupLinesIntoChunks(lines);
    expect(performance.now() - start).toBeLessThan(100);
  });

  it("10. stripAnsi sobre una línea con color ANSI; sin ANSI devuelve la línea igual", () => {
    // ESC via fromCharCode: evita sembrar el byte 0x1B crudo en el archivo fuente.
    const esc = String.fromCharCode(27);
    expect(stripAnsi(`${esc}[31mrojo${esc}[0m`)).toBe("rojo");
    expect(stripAnsi("sin color")).toBe("sin color");
  });

  it("11. una línea de 200000 caracteres sin saltos: no lanza y termina en < 100 ms", () => {
    const huge = ln("x".repeat(200_000));
    const start = performance.now();
    expect(() => groupLinesIntoChunks([huge])).not.toThrow();
    expect(performance.now() - start).toBeLessThan(100);
  });
});
