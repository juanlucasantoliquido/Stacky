/**
 * Tests del NodeErrorBoundary — el error boundary que envuelve cada
 * TicketNodeCard en TicketGraphView. Diseñado en Fase 2 del lifecycle
 * remediation plan para aislar errores de un nodo sin blanquear toda
 * la graph view.
 *
 * Cubre:
 *  - Render normal (sin error) → children visibles.
 *  - Hijo que lanza durante render → fallback con ADO id y mensaje.
 *  - getDerivedStateFromError mantiene el state hasError=true entre renders.
 *  - El componente captura errores de descendientes anidados.
 */
// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NodeErrorBoundary } from "../TicketGraphView";

// Silenciar el console.error que React loguea cuando un boundary captura
// un error (no aporta al test, ensucia el output).
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();  // vitest no llama cleanup automático sin configurar globals
  vi.restoreAllMocks();
});

// ── Test fixtures ─────────────────────────────────────────────────────────────

function ThrowingChild({ message = "boom" }: { message?: string }): React.ReactElement {
  throw new Error(message);
}

function HealthyChild({ children }: { children?: React.ReactNode }): React.ReactElement {
  return <div data-testid="healthy">{children ?? "ok"}</div>;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("NodeErrorBoundary", () => {
  it("renders children when there is no error", () => {
    render(
      <NodeErrorBoundary adoId={123}>
        <HealthyChild>hello</HealthyChild>
      </NodeErrorBoundary>,
    );

    expect(screen.getByTestId("healthy")).toBeTruthy();
    expect(screen.getByTestId("healthy").textContent).toBe("hello");
  });

  it("shows fallback with ADO id when a child throws during render", () => {
    render(
      <NodeErrorBoundary adoId={27698}>
        <ThrowingChild message="boundary catches this" />
      </NodeErrorBoundary>,
    );

    // Fallback visible
    const alert = screen.getByRole("alert");
    expect(alert).toBeTruthy();
    expect(alert.textContent).toContain("ADO-27698");
    expect(alert.textContent).toContain("boundary catches this");
    expect(alert.textContent).toContain("Recargá la página");
  });

  it("shows '?' when adoId prop is not provided", () => {
    render(
      <NodeErrorBoundary>
        <ThrowingChild message="no ado id" />
      </NodeErrorBoundary>,
    );

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("ADO-?");
  });

  it("falls back to generic message when error has no message", () => {
    function ThrowWithoutMessage(): React.ReactElement {
      throw new Error();
    }

    render(
      <NodeErrorBoundary adoId={1}>
        <ThrowWithoutMessage />
      </NodeErrorBoundary>,
    );

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("error inesperado");
  });

  it("isolates failures so siblings keep rendering", () => {
    // Múltiples boundaries hermanos. Uno lanza, otro no. El segundo debe
    // mantenerse vivo y visible. Esto valida la promesa del diseño: un nodo
    // roto NO desmonta el árbol completo.
    render(
      <div>
        <NodeErrorBoundary adoId={111}>
          <ThrowingChild message="first crashes" />
        </NodeErrorBoundary>
        <NodeErrorBoundary adoId={222}>
          <HealthyChild>still alive</HealthyChild>
        </NodeErrorBoundary>
      </div>,
    );

    // El primero muestra fallback con ADO-111
    const alerts = screen.getAllByRole("alert");
    expect(alerts.length).toBe(1);
    expect(alerts[0].textContent).toContain("ADO-111");

    // El segundo sigue renderizando normal
    expect(screen.getByTestId("healthy").textContent).toBe("still alive");
  });

  it("catches errors thrown by deeply nested descendants", () => {
    function Wrapper({ children }: { children: React.ReactNode }): React.ReactElement {
      return <section><div>{children}</div></section>;
    }

    render(
      <NodeErrorBoundary adoId={42}>
        <Wrapper>
          <Wrapper>
            <ThrowingChild message="deep" />
          </Wrapper>
        </Wrapper>
      </NodeErrorBoundary>,
    );

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("ADO-42");
    expect(alert.textContent).toContain("deep");
  });
});
