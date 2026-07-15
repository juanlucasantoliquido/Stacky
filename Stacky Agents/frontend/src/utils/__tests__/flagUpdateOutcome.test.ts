import { describe, expect, it } from "vitest";
import { classifyFlagUpdateOutcome } from "../flagUpdateOutcome";

describe("classifyFlagUpdateOutcome (plan 135 F0)", () => {
  it("ok sin restart es ok silencioso", () => {
    expect(classifyFlagUpdateOutcome({ ok: true })).toEqual({ kind: "ok", message: null });
  });

  it("ok con restart_required_keys es warning con las keys", () => {
    const r = classifyFlagUpdateOutcome({ ok: true, restart_required_keys: ["STACKY_X", "STACKY_Y"] });
    expect(r.kind).toBe("warning");
    expect(r.message).toBe("Guardado. Requiere reiniciar el backend: STACKY_X, STACKY_Y");
  });

  it("no-ok es error con el mensaje del backend", () => {
    expect(classifyFlagUpdateOutcome({ ok: false, error: "boom" })).toEqual({
      kind: "error",
      message: "boom",
    });
  });

  it("no-ok sin mensaje cae al copy default", () => {
    const r = classifyFlagUpdateOutcome({ ok: false });
    expect(r.kind).toBe("error");
    expect(r.message).toBe("Error al guardar la flag");
  });
});
