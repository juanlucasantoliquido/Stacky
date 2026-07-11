/**
 * ExecutionInsightBlock.test.tsx — Plan 117 F4.
 *
 * NOTA DE ENTORNO (bloqueo preexistente): este checkout no tiene jsdom/entorno DOM
 * configurado para vitest, así que los tests basados en @testing-library/react NO
 * corren (el propio WeeklyDigestCard.test.tsx falla con "no tests" por el mismo gap,
 * verificado). Test-first, listo para correr cuando se resuelva el entorno. La
 * verificación de tipos (tsc --noEmit) SÍ corre y cubre el componente.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import ExecutionInsightBlock from "../ExecutionInsightBlock";
import type { ExecutionLocalInsight } from "../../api/endpoints";

vi.mock("../../api/endpoints", () => ({
  LocalLlmApi: { generateInsight: vi.fn() },
}));
import { LocalLlmApi } from "../../api/endpoints";

const DONE: ExecutionLocalInsight = {
  state: "done", tldr: "resumen ok", labels: ["a", "b"], risk: "high",
  probable_cause: "causa x", evidence: "ev y", next_step: "paso z",
  model: "qwen", generated_at: "2026-07-10T00:00:00Z", attempts: 1,
};

describe("ExecutionInsightBlock", () => {
  it("renders tldr labels and risk when insight done", () => {
    render(<ExecutionInsightBlock executionId={1} insight={DONE} />);
    expect(screen.getByText("resumen ok")).toBeTruthy();
    expect(screen.getByText(/riesgo: high/)).toBeTruthy();
  });

  it("renders triage rows when failure fields present", () => {
    render(<ExecutionInsightBlock executionId={1} insight={DONE} />);
    expect(screen.getByText(/Causa probable:/)).toBeTruthy();
    expect(screen.getByText(/Siguiente paso sugerido:/)).toBeTruthy();
  });

  it("renders generate button when insight missing and click calls generateInsight", async () => {
    (LocalLlmApi.generateInsight as any).mockResolvedValue({ ok: true });
    const onRegenerated = vi.fn();
    render(<ExecutionInsightBlock executionId={7} insight={null} onRegenerated={onRegenerated} />);
    fireEvent.click(screen.getByText(/Generar insight/));
    await waitFor(() => expect(LocalLlmApi.generateInsight).toHaveBeenCalledWith(7));
    await waitFor(() => expect(onRegenerated).toHaveBeenCalled());
  });

  it("shows flag hint on local_insights_disabled error", async () => {
    (LocalLlmApi.generateInsight as any).mockRejectedValue(new Error("404 local_insights_disabled"));
    render(<ExecutionInsightBlock executionId={7} insight={null} />);
    fireEvent.click(screen.getByText(/Generar insight/));
    await waitFor(() => expect(screen.getByText(/Configuración → Arnés/)).toBeTruthy());
  });
});
