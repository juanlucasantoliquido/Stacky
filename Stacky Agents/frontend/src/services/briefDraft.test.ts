import { describe, expect, it } from "vitest";
import { briefDraftKey, clearBriefDraft, readBriefDraft, writeBriefDraft, type StorageLike } from "./briefDraft";

function fakeStorage(): StorageLike {
  const map = new Map<string, string>();
  return {
    getItem: (key) => (map.has(key) ? map.get(key)! : null),
    setItem: (key, value) => { map.set(key, value); },
    removeItem: (key) => { map.delete(key); },
  };
}

describe("briefDraft (plan 136 F0)", () => {
  it("write+read roundtrip", () => {
    const s = fakeStorage();
    writeBriefDraft(s, "proj-x", "hola mundo");
    expect(readBriefDraft(s, "proj-x")).toBe("hola mundo");
  });

  it("claves distintas por proyecto", () => {
    const s = fakeStorage();
    writeBriefDraft(s, "A", "brief de A");
    writeBriefDraft(s, "B", "brief de B");
    expect(readBriefDraft(s, "A")).toBe("brief de A");
    expect(readBriefDraft(s, "B")).toBe("brief de B");
  });

  it("project null usa la clave _global", () => {
    const s = fakeStorage();
    writeBriefDraft(s, null, "sin proyecto");
    expect(readBriefDraft(s, null)).toBe("sin proyecto");
  });

  it("write con string vacío o whitespace hace removeItem", () => {
    const s = fakeStorage();
    writeBriefDraft(s, "A", "algo");
    writeBriefDraft(s, "A", "   ");
    expect(readBriefDraft(s, "A")).toBe("");
  });

  it("clear → read vacío", () => {
    const s = fakeStorage();
    writeBriefDraft(s, "A", "algo");
    clearBriefDraft(s, "A");
    expect(readBriefDraft(s, "A")).toBe("");
  });

  it("storage null → read vacío, write/clear no lanzan", () => {
    expect(readBriefDraft(null, "A")).toBe("");
    expect(() => writeBriefDraft(null, "A", "x")).not.toThrow();
    expect(() => clearBriefDraft(null, "A")).not.toThrow();
  });

  it("storage cuyo setItem lanza no propaga", () => {
    const s: StorageLike = {
      getItem: () => null,
      setItem: () => { throw new Error("cuota llena"); },
      removeItem: () => {},
    };
    expect(() => writeBriefDraft(s, "A", "x")).not.toThrow();
  });

  it("contrato de clave congelado", () => {
    expect(briefDraftKey("X")).toBe("stacky.epicBriefDraft.v1:X");
    expect(briefDraftKey(null)).toBe("stacky.epicBriefDraft.v1:_global");
  });
});
