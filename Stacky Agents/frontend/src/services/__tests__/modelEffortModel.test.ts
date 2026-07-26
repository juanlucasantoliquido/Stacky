// Plan 212 F7 — la degradación se ve o no existe.
import { describe, it, expect } from "vitest";
import { describeDowngrade } from "../modelEffortModel";

describe("describeDowngrade", () => {
  it("sin metadata no dice nada", () => {
    expect(describeDowngrade(null)).toBeNull();
    expect(describeDowngrade(undefined)).toBeNull();
    expect(describeDowngrade({})).toBeNull();
  });

  it("sin degradación no dice nada", () => {
    expect(
      describeDowngrade({
        model_effort: {
          requested_model: "claude-opus-4-8",
          effective_model: "claude-opus-4-8",
          downgraded: false,
        },
      })
    ).toBeNull();
  });

  it("con degradación arma el par solicitado → ejecutado con la razón", () => {
    const linea = describeDowngrade({
      model_effort: {
        requested_model: "claude-opus-4-8",
        effective_model: "claude-sonnet-5",
        requested_effort: "xhigh",
        effective_effort: "high",
        downgraded: true,
        reason: "user-override claude-opus-4-8 -> clamp §5.2",
      },
    });

    expect(linea).toBe(
      "Solicitado claude-opus-4-8/xhigh → ejecutado claude-sonnet-5/high — user-override claude-opus-4-8 -> clamp §5.2"
    );
  });

  it("sin razón no deja el guion colgando", () => {
    const linea = describeDowngrade({
      model_effort: {
        requested_model: "claude-opus-4-8",
        effective_model: "claude-sonnet-5",
        downgraded: true,
      },
    });

    expect(linea).toBe("Solicitado claude-opus-4-8 → ejecutado claude-sonnet-5");
  });

  it("un model_effort corrupto no rompe el drawer", () => {
    expect(describeDowngrade({ model_effort: "no soy un objeto" })).toBeNull();
  });
});
