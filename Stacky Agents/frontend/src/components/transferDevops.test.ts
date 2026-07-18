import { describe, expect, it } from "vitest";
import { credentialsChecklist, skippedNote } from "./transferDevops";

describe("credentialsChecklist", () => {
  it("devuelve listas vacías cuando no hay resultado", () => {
    expect(credentialsChecklist(undefined)).toEqual({ pending: [], neverSet: [] });
  });

  it("separa pending de neverSet", () => {
    const res = {
      devops: { credentials_pending: ["a", "b"], credentials_never_set: ["c"] },
    };
    expect(credentialsChecklist(res)).toEqual({ pending: ["a", "b"], neverSet: ["c"] });
  });

  it("tolera un devops sin las claves de credenciales", () => {
    expect(credentialsChecklist({ devops: {} })).toEqual({ pending: [], neverSet: [] });
  });
});

describe("skippedNote", () => {
  it("null cuando no hay secciones omitidas", () => {
    expect(skippedNote(undefined)).toBeNull();
    expect(skippedNote({ skipped_sections: [] })).toBeNull();
  });

  it("texto con una sección", () => {
    expect(skippedNote({ skipped_sections: ["devopsServers"] })).toBe(
      "Secciones omitidas: devopsServers",
    );
  });

  it("texto con dos secciones", () => {
    expect(skippedNote({ skipped_sections: ["devopsServers", "devopsApps"] })).toBe(
      "Secciones omitidas: devopsServers, devopsApps",
    );
  });
});
