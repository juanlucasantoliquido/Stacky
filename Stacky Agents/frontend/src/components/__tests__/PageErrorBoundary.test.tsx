/**
 * NOTA DE ENTORNO: este archivo no puede ejecutarse en este checkout porque
 * faltan `@testing-library/react` y un entorno jsdom en node_modules/vitest
 * config (gap preexistente, no introducido por este cambio — se reproduce
 * igual en ActiveRunsPanel.test.tsx y en cualquier test de componente ya
 * existente, p.ej. WeeklyDigestCard.test.tsx). Queda listo para correr en
 * cuanto se resuelva ese gap de entorno.
 */
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, afterEach } from "vitest";
import PageErrorBoundary from "../PageErrorBoundary";

function Bomb(): never {
  throw new Error("boom de render");
}

describe("PageErrorBoundary (plan 135 F4)", () => {
  afterEach(() => {
    cleanup();
  });

  it("renderiza el fallback con el mensaje cuando un hijo lanza", () => {
    render(
      <PageErrorBoundary resetKey="a">
        <Bomb />
      </PageErrorBoundary>,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toMatch(/Esta pestaña falló al renderizar/);
    expect(alert.textContent).toMatch(/boom de render/);
  });

  it("Reintentar resetea el boundary y re-renderiza los hijos", () => {
    let shouldThrow = true;
    function Flaky() {
      if (shouldThrow) throw new Error("boom de render");
      return <div>vivo</div>;
    }
    render(
      <PageErrorBoundary resetKey="a">
        <Flaky />
      </PageErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeDefined();
    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: /reintentar/i }));
    expect(screen.getByText("vivo")).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("cambiar resetKey resetea el boundary", () => {
    const { rerender } = render(
      <PageErrorBoundary resetKey="a">
        <Bomb />
      </PageErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeDefined();
    rerender(
      <PageErrorBoundary resetKey="b">
        <div>vivo</div>
      </PageErrorBoundary>,
    );
    expect(screen.getByText("vivo")).toBeDefined();
  });

  it("sin error renderiza los hijos tal cual", () => {
    render(
      <PageErrorBoundary resetKey="a">
        <div>texto normal</div>
      </PageErrorBoundary>,
    );
    expect(screen.getByText("texto normal")).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
