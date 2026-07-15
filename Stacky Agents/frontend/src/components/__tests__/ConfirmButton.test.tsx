/**
 * NOTA DE ENTORNO: este archivo no puede ejecutarse en este checkout porque
 * faltan `@testing-library/react` y un entorno jsdom en node_modules/vitest
 * config (gap preexistente, no introducido por este cambio — se reproduce
 * igual en ActiveRunsPanel.test.tsx y en cualquier test de componente ya
 * existente, p.ej. WeeklyDigestCard.test.tsx). Queda listo para correr en
 * cuanto se resuelva ese gap de entorno.
 */
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { vi, describe, it, expect, afterEach, beforeEach } from "vitest";
import ConfirmButton from "../ConfirmButton";

describe("ConfirmButton (plan 136 F3)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("render inicial muestra label", () => {
    render(<ConfirmButton label="Borrar" onConfirm={() => {}} />);
    expect(screen.getByRole("button").textContent).toBe("Borrar");
  });

  it("primer click NO llama onConfirm y muestra confirmLabel", () => {
    const onConfirm = vi.fn();
    render(<ConfirmButton label="Borrar" confirmLabel="⚠ Confirmar" onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole("button").textContent).toBe("⚠ Confirmar");
  });

  it("segundo click llama onConfirm exactamente 1 vez", () => {
    const onConfirm = vi.fn();
    render(<ConfirmButton label="Borrar" onConfirm={onConfirm} />);
    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("avanzar 4001ms tras el primer click desarma y un click posterior no ejecuta", () => {
    const onConfirm = vi.fn();
    render(<ConfirmButton label="Borrar" onConfirm={onConfirm} timeoutMs={4000} />);
    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    vi.advanceTimersByTime(4001);
    expect(btn.textContent).toBe("Borrar");
    fireEvent.click(btn);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("busy:true deshabilita el botón", () => {
    render(<ConfirmButton label="Borrar" onConfirm={() => {}} busy />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
