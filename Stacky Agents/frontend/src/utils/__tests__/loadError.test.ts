import { describe, expect, it } from "vitest";
import { formatLoadErrorMessage } from "../loadError";

describe("formatLoadErrorMessage (plan 135 F0)", () => {
  it("devuelve el message de un Error", () => {
    const msg = formatLoadErrorMessage(new Error("500 INTERNAL SERVER ERROR: boom"));
    expect(msg).toContain("500 INTERNAL SERVER ERROR: boom");
  });

  it("trunca mensajes largos a maxLen con elipsis", () => {
    const long = "x".repeat(500);
    const msg = formatLoadErrorMessage(new Error(long));
    expect(msg.length).toBe(140);
    expect(msg.endsWith("…")).toBe(true);
  });

  it("colapsa saltos de línea y espacios múltiples", () => {
    const msg = formatLoadErrorMessage(new Error("a\n\n  b\tc"));
    expect(msg).toBe("a b c");
  });

  it("acepta strings crudos", () => {
    expect(formatLoadErrorMessage("timeout")).toBe("timeout");
  });

  it("cae a 'error desconocido' ante null/undefined/objeto raro", () => {
    expect(formatLoadErrorMessage(null)).toBe("error desconocido");
    expect(formatLoadErrorMessage(undefined)).toBe("error desconocido");
    expect(formatLoadErrorMessage({})).toBe("error desconocido");
  });
});
