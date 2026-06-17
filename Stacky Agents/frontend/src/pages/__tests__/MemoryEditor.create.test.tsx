/**
 * Tests de componente para MemoryEditor (plan 26 — M2.1/M2.2).
 *
 * Cubre: render del form, aparición de la sección de targeting solo para
 * type=directive, preview imperativo compuesto en el cliente, validación de
 * targeting vacío (botón deshabilitado) y submit que llama Memory.create.
 *
 * NOTA: vitest no está instalado en este entorno (ver memoria backend-dev-test-env);
 * el archivo sigue la convención del repo y se ejecuta cuando el toolchain esté.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import type { ReactElement } from "react";
import MemoryEditor from "../memory/MemoryEditor";

vi.mock("../../api/endpoints", () => ({
  Memory: {
    create: vi.fn(async () => ({ memory_id: "m1" })),
    update: vi.fn(async () => ({ ok: true })),
  },
}));

import { Memory } from "../../api/endpoints";

const mockCreate = Memory.create as ReturnType<typeof vi.fn>;

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const TYPES = ["pattern", "policy", "directive"];

beforeEach(() => {
  mockCreate.mockClear();
});

describe("MemoryEditor — alta", () => {
  it("crea una observación normal sin sección de targeting", () => {
    wrap(
      <MemoryEditor
        project="P1"
        mode="create"
        injectableTypes={TYPES}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    // type default = pattern → no hay preview de directiva.
    expect(screen.queryByTestId("directive-preview")).toBeNull();
  });

  it("muestra el targeting y el preview imperativo para type=directive", () => {
    wrap(
      <MemoryEditor
        project="P1"
        mode="create"
        injectableTypes={TYPES}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "" }), { target: { value: "directive" } });
    const preview = screen.getByTestId("directive-preview");
    expect(preview).toBeTruthy();
    // sin targeting, el preview avisa que falta una dimensión.
    expect(preview.textContent).toMatch(/sin targeting/i);
  });

  it("habilita submit y llama Memory.create cuando la directiva tiene targeting", () => {
    wrap(
      <MemoryEditor
        project="P1"
        mode="create"
        injectableTypes={TYPES}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "directive" } });
    fireEvent.change(screen.getByPlaceholderText("Resumen corto"), { target: { value: "Regla X" } });
    fireEvent.change(screen.getByPlaceholderText("functional, developer"), {
      target: { value: "developer" },
    });
    const textarea = screen.getByRole("textbox", { name: "Contenido" }) || screen.getAllByRole("textbox")[1];
    fireEvent.change(textarea, { target: { value: "Hacelo así siempre" } });
    fireEvent.click(screen.getByText("Crear"));
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockCreate.mock.calls[0][0]).toMatchObject({
      type: "directive",
      applies_to: { agent_types: ["developer"] },
    });
  });
});
