/**
 * errorAnalysisModel.test.ts — Plan 127 F6. vitest, TS puro.
 */
import { describe, expect, it } from "vitest";
import { disabledHint, shouldOfferErrorAnalysis } from "./errorAnalysisModel";

describe("shouldOfferErrorAnalysis", () => {
  it("error_sin_metadata_true", () => {
    expect(shouldOfferErrorAnalysis("error", null)).toBe(true);
  });

  it("completed_limpio_false", () => {
    expect(shouldOfferErrorAnalysis("completed", null)).toBe(false);
  });

  it("completed_con_metadata_error_analysis_true", () => {
    expect(
      shouldOfferErrorAnalysis("completed", { error_analysis: { analysis: "algo" } }),
    ).toBe(true);
  });

  it("needs_review_true", () => {
    expect(shouldOfferErrorAnalysis("needs_review", null)).toBe(true);
  });
});

describe("disabledHint", () => {
  it("hint_404", () => {
    expect(disabledHint(404)).toBe(
      "El análisis con IA local está apagado en el Arnés: reactivá STACKY_EXEC_ERROR_ANALYSIS_ENABLED y LOCAL_LLM_ENABLED.",
    );
  });

  it("hint_502", () => {
    expect(disabledHint(502)).toBe("El modelo local no respondió: verificá que Ollama esté corriendo.");
  });

  it("hint_500_generico", () => {
    expect(disabledHint(500)).toBe("No se pudo analizar (HTTP 500).");
  });
});
