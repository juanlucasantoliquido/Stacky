/**
 * errorAnalysisModel.ts — Plan 127 F6 (C1). PURO: sin fetch, sin React, sin efectos.
 * Elegibilidad y textos de degradación para el bloque de análisis de error.
 */

/**
 * true si status ∈ {"error","needs_review"} (para ofrecer el botón aunque no
 * haya análisis aún) o si ya existe un análisis persistido en metadata
 * (para mostrar el resultado incluso si el status cambió, p.ej. tras reintento).
 */
export function shouldOfferErrorAnalysis(
  status: string,
  metadata: Record<string, unknown> | null,
): boolean {
  if (status === "error" || status === "needs_review") return true;
  return Boolean(metadata && metadata.error_analysis);
}

/** Texto accionable por código HTTP (H10, redactado para default ON). */
export function disabledHint(httpStatus: number): string {
  if (httpStatus === 404) {
    return "El análisis con IA local está apagado en el Arnés: reactivá STACKY_EXEC_ERROR_ANALYSIS_ENABLED y LOCAL_LLM_ENABLED.";
  }
  if (httpStatus === 502) {
    return "El modelo local no respondió: verificá que Ollama esté corriendo.";
  }
  return `No se pudo analizar (HTTP ${httpStatus}).`;
}
