/**
 * EgressSentinelBlock.test.tsx — Plan 121 F5.
 *
 * NOTA DE ENTORNO (bloqueo preexistente, mismo gap documentado en
 * ExecutionInsightBlock.test.tsx): este checkout no tiene @testing-library/react
 * instalado, así que los tests basados en @testing-library/react NO corren.
 * Test-first, listo para correr cuando se resuelva el entorno. La verificación de
 * tipos (tsc --noEmit) SÍ corre y cubre el componente.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import EgressSentinelBlock from "../EgressSentinelBlock";
import type { EgressSentinelData } from "../EgressSentinelBlock";

const CLEAN: EgressSentinelData = { status: "clean", findings: [], deterministic_classes: [] };

const WITH_FINDING: EgressSentinelData = {
  status: "findings",
  findings: [
    { data_class: "secrets", severity: "critical", excerpt_masked: "pass…***", rationale: "clave en claro" },
  ],
  deterministic_classes: ["secrets"],
};

describe("EgressSentinelBlock", () => {
  it("renders nothing without sentinel data", () => {
    const { container } = render(<EgressSentinelBlock sentinel={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders clean chip when status clean", () => {
    render(<EgressSentinelBlock sentinel={CLEAN} />);
    expect(screen.getByText("Egreso: limpio")).toBeTruthy();
  });

  it("renders masked findings with severity", () => {
    render(<EgressSentinelBlock sentinel={WITH_FINDING} />);
    expect(screen.getByText("Posible fuga en el prompt")).toBeTruthy();
    expect(screen.getByText("critical")).toBeTruthy();
    expect(screen.getByText("pass…***")).toBeTruthy();
  });

  it("never renders unmasked long tokens", () => {
    const longToken: EgressSentinelData = {
      status: "findings",
      findings: [
        { data_class: "secrets", severity: "critical", excerpt_masked: "ghp_…***", rationale: "x" },
      ],
      deterministic_classes: [],
    };
    render(<EgressSentinelBlock sentinel={longToken} />);
    expect(screen.queryByText(/ghp_[A-Za-z0-9]{20,}/)).toBeNull();
  });
});
