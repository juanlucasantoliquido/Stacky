/**
 * NOTA DE ENTORNO: este archivo no puede ejecutarse en este checkout porque
 * faltan `@testing-library/react` y un entorno jsdom en node_modules/vitest
 * config (gap preexistente, no introducido por este cambio — se reproduce
 * igual en ActiveRunsPanel.test.tsx y en cualquier test de componente ya
 * existente, p.ej. WeeklyDigestCard.test.tsx). Queda listo para correr en
 * cuanto se resuelva ese gap de entorno.
 */
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { vi, describe, it, expect, afterEach } from "vitest";
import LoadErrorState from "../LoadErrorState";

describe("LoadErrorState (plan 135 F1)", () => {
  afterEach(() => {
    cleanup();
  });

  it("muestra el copy de error con el sujeto", () => {
    render(<LoadErrorState what="los tickets" />);
    expect(screen.getByText(/No se pudieron cargar los tickets/)).toBeDefined();
  });

  it("muestra el detalle formateado del error", () => {
    render(<LoadErrorState what="los tickets" error={new Error("500 X: boom")} />);
    expect(screen.getByText(/boom/)).toBeDefined();
  });

  it("el botón Reintentar dispara onRetry", () => {
    const onRetry = vi.fn();
    render(<LoadErrorState what="los tickets" onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: /reintentar/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("sin onRetry no renderiza botón", () => {
    render(<LoadErrorState what="los tickets" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("la variante compact renderiza en una línea con role alert", () => {
    render(<LoadErrorState what="los tickets" compact />);
    const alert = screen.getByRole("alert");
    expect(alert).toBeDefined();
    expect(alert.textContent).toContain("los tickets");
  });
});
