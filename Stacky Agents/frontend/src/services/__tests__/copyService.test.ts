/**
 * copyService.test.ts — Plan 194 F1. Casos enumerados del doc (14).
 * G4: sin jsdom; se stubbean navigator/document/ClipboardItem con vi.stubGlobal.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/copyService.test.ts
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { copyText, copyRichText, resolveCopyExportEnabled } from "../copyService";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function makeDocStub(opts: {
  execCommand: () => boolean;
  activeElement?: { focus: () => void } | null;
  getSelection?: () => unknown;
}) {
  const appendChild = vi.fn();
  const removeChild = vi.fn();
  const select = vi.fn();
  const ta = { value: "", setAttribute: vi.fn(), select, style: { cssText: "" } };
  const doc: Record<string, unknown> = {
    createElement: vi.fn(() => ta),
    body: { appendChild, removeChild },
    execCommand: vi.fn(opts.execCommand),
  };
  if (opts.activeElement !== undefined) doc.activeElement = opts.activeElement;
  if (opts.getSelection) doc.getSelection = opts.getSelection;
  return { doc, appendChild, removeChild, ta };
}

describe("copyService.copyText", () => {
  it("caso 1 — texto vacío ⇒ empty y no llama writeText", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const r = await copyText("");
    expect(r).toEqual({ ok: false, reason: "empty" });
    expect(writeText).not.toHaveBeenCalled();
  });

  it("caso 2 — writeText resuelve ⇒ clipboard con el texto exacto", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const r = await copyText("hola mundo");
    expect(r).toEqual({ ok: true, method: "clipboard" });
    expect(writeText).toHaveBeenCalledWith("hola mundo");
  });

  it("caso 3 — writeText rechaza + execCommand true ⇒ execCommand y textarea agregado/removido", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("insecure"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const { doc, appendChild, removeChild } = makeDocStub({ execCommand: () => true });
    vi.stubGlobal("document", doc);
    const r = await copyText("ruta/abs");
    expect(r).toEqual({ ok: true, method: "execCommand" });
    expect(appendChild).toHaveBeenCalledTimes(1);
    expect(removeChild).toHaveBeenCalledTimes(1);
  });

  it("caso 4 — writeText rechaza + execCommand false ⇒ denied", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("insecure"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const { doc } = makeDocStub({ execCommand: () => false });
    vi.stubGlobal("document", doc);
    const r = await copyText("x");
    expect(r).toEqual({ ok: false, reason: "denied" });
  });

  it("caso 5 — sin navigator ni document ⇒ unavailable", async () => {
    vi.stubGlobal("navigator", undefined);
    vi.stubGlobal("document", undefined);
    const r = await copyText("x");
    expect(r).toEqual({ ok: false, reason: "unavailable" });
  });

  it("caso 11 — (C1) fallback preserva foco; sin getSelection no rompe", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("insecure"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const focus = vi.fn();
    const { doc } = makeDocStub({ execCommand: () => true, activeElement: { focus } });
    vi.stubGlobal("document", doc);
    const r = await copyText("x");
    expect(r).toEqual({ ok: true, method: "execCommand" });
    expect(focus).toHaveBeenCalledTimes(1);
  });
});

describe("copyService.copyRichText", () => {
  it("caso 12 — (§4.11) clipboard.write + ClipboardItem ⇒ richClipboard con text/html+text/plain", async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { write } });
    const seen: Record<string, unknown>[] = [];
    class ClipboardItemStub {
      constructor(parts: Record<string, unknown>) {
        seen.push(parts);
      }
    }
    vi.stubGlobal("ClipboardItem", ClipboardItemStub);
    const r = await copyRichText("<b>x</b>", "x");
    expect(r).toEqual({ ok: true, method: "richClipboard" });
    expect(write).toHaveBeenCalledTimes(1);
    expect(seen).toHaveLength(1);
    expect(Object.keys(seen[0])).toEqual(["text/html", "text/plain"]);
  });

  it("caso 13 — (§4.11) sin clipboard.write ⇒ degrada a copyText(plain)", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } }); // sin .write
    vi.stubGlobal("ClipboardItem", undefined);
    const r = await copyRichText("<b>x</b>", "x");
    expect(r).toEqual({ ok: true, method: "clipboard" });
    expect(writeText).toHaveBeenCalledWith("x"); // el PLAIN, no el html
  });

  it("caso 14 — (§4.11) plain vacío ⇒ empty", async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { write } });
    const r = await copyRichText("<b>x</b>", "");
    expect(r).toEqual({ ok: false, reason: "empty" });
  });
});

describe("copyService.resolveCopyExportEnabled (wrapper de flagGate, 197 §6.1)", () => {
  it("caso 6 — undefined ⇒ true (fail-open)", () => {
    expect(resolveCopyExportEnabled(undefined)).toBe(true);
  });
  it("caso 7 — [] (flag ausente) ⇒ true", () => {
    expect(resolveCopyExportEnabled([])).toBe(true);
  });
  it("caso 8 — value false ⇒ false", () => {
    expect(resolveCopyExportEnabled([{ key: "STACKY_COPY_EXPORT_ENABLED", value: false }])).toBe(false);
  });
  it("caso 9 — value true ⇒ true", () => {
    expect(resolveCopyExportEnabled([{ key: "STACKY_COPY_EXPORT_ENABLED", value: true }])).toBe(true);
  });
  it("caso 10 — value string 'true' ⇒ true (fail-open de serie: SOLO false literal apaga)", () => {
    // DESVIACIÓN documentada del doc 194 (que pedía false): 194 delega en flagGate
    // (197 §6.1 'wrapper sobre flagGate'), cuya semántica congelada apaga SOLO con
    // el boolean false literal. En producción el backend entrega bool para type="bool",
    // así que el borde string es inerte.
    expect(resolveCopyExportEnabled([{ key: "STACKY_COPY_EXPORT_ENABLED", value: "true" }])).toBe(true);
  });
});
