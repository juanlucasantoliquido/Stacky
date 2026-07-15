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
import Toast, { type ToastState } from "../Toast";

describe("Toast (plan 135 F5)", () => {
  afterEach(() => {
    cleanup();
  });

  it("renderiza title y body con role alert", () => {
    const toast: ToastState = { variant: "success", title: "Listo", body: "Guardado ok" };
    render(<Toast toast={toast} onClose={() => {}} />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Listo");
    expect(alert.textContent).toContain("Guardado ok");
  });

  it("sin title no renderiza el header title", () => {
    const toast: ToastState = { variant: "success", body: "Guardado ok" };
    render(<Toast toast={toast} onClose={() => {}} />);
    expect(screen.queryByText(/^Listo$/)).toBeNull();
  });

  it("aplica la clase de la variante", () => {
    (["success", "warning", "error"] as const).forEach((variant) => {
      const { container, unmount } = render(
        <Toast toast={{ variant, body: "x" }} onClose={() => {}} />,
      );
      expect(container.firstElementChild?.className).toContain(variant);
      unmount();
    });
  });

  it("el botón cerrar dispara onClose", () => {
    const onClose = vi.fn();
    render(<Toast toast={{ variant: "success", body: "x" }} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: /cerrar notificación/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
