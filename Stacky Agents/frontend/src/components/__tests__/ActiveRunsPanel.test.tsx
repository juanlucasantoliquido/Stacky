/**
 * Tests de componente para ActiveRunsPanel.
 *
 * Cubre el comportamiento nuevo pedido por el operador (2026-07-09): el panel
 * tapaba botones al quedar fijo arriba-a-la-derecha sin forma de cerrarlo ni
 * moverlo. Se agrega: colapsar a un badge mínimo (que sigue mostrando el
 * conteo de runs activos), volver a expandir, ciclar la posición entre las 4
 * esquinas, y que ambas preferencias persistan en localStorage entre renders
 * (simulando un F5). También cubre — sin cambios de comportamiento — que
 * cancelar un run sigue funcionando.
 *
 * NOTA DE ENTORNO: este archivo no puede ejecutarse en este checkout porque
 * faltan `@testing-library/react` y un entorno jsdom en node_modules/vitest
 * config (gap preexistente, no introducido por este cambio — se reproduce
 * igual en ActiveRunsPanel.test.tsx y en cualquier test de componente ya
 * existente, p.ej. WeeklyDigestCard.test.tsx). Queda listo para correr en
 * cuanto se resuelva ese gap de entorno.
 */

import { render, screen, waitFor, fireEvent, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import type { ReactElement } from "react";
import ActiveRunsPanel from "../ActiveRunsPanel";
import type { AgentExecution } from "../../types";

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock("../../api/endpoints", () => ({
  Executions: {
    list: vi.fn(),
    cancel: vi.fn(),
  },
}));

import { Executions } from "../../api/endpoints";

const mockList = Executions.list as ReturnType<typeof vi.fn>;
const mockCancel = Executions.cancel as ReturnType<typeof vi.fn>;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function wrap(ui: ReactElement) {
  return render(
    <QueryClientProvider client={makeQueryClient()}>{ui}</QueryClientProvider>,
  );
}

const RUN: AgentExecution = {
  id: 42,
  ticket_id: 1001,
  agent_type: "developer",
  status: "running",
  input_context: [],
  chain_from: [],
  started_by: "operator",
  started_at: "2026-07-09T10:00:00Z",
};

/** Responde según el status pedido: "running" trae el run de prueba, el resto vacío. */
function mockRuns(runs: AgentExecution[]) {
  mockList.mockImplementation(
    async (q: { status?: string }) => (q.status === "running" ? runs : []),
  );
}

describe("ActiveRunsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockCancel.mockResolvedValue({ ok: true, execution_id: RUN.id });
  });

  afterEach(() => {
    cleanup();
  });

  it("no renderiza nada cuando no hay runs activos", async () => {
    mockRuns([]);
    const { container } = wrap(<ActiveRunsPanel />);
    await waitFor(() => expect(mockList).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it("lista los runs activos y permite cancelar uno (confirmando el diálogo)", async () => {
    mockRuns([RUN]);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));

    await waitFor(() => expect(mockCancel).toHaveBeenCalledWith(42));
  });

  it("no cancela si el operador rechaza el diálogo de confirmación", async () => {
    mockRuns([RUN]);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));

    expect(mockCancel).not.toHaveBeenCalled();
  });

  it("colapsa a un badge mínimo con el conteo y permite volver a expandir", async () => {
    mockRuns([RUN]);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: /ocultar panel/i }));

    // El panel completo desaparece pero queda el badge con el conteo.
    expect(screen.queryByText("#42")).toBeNull();
    const badge = screen.getByRole("button", {
      name: /mostrar ejecuciones activas/i,
    });
    expect(badge.textContent).toContain("1");

    fireEvent.click(badge);
    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
  });

  it("persiste el colapso en localStorage entre renders (sobrevive a un F5)", async () => {
    mockRuns([RUN]);
    const first = wrap(<ActiveRunsPanel />);
    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: /ocultar panel/i }));
    expect(localStorage.getItem("stacky.activeRunsPanel.collapsed")).toBe("true");

    first.unmount();
    wrap(<ActiveRunsPanel />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /mostrar ejecuciones activas/i }),
      ).toBeDefined(),
    );
    expect(screen.queryByText("#42")).toBeNull();
  });

  it("cicla la posición entre las 4 esquinas y la persiste en localStorage", async () => {
    mockRuns([RUN]);
    wrap(<ActiveRunsPanel />);
    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());

    const moveBtn = screen.getByRole("button", { name: /mover panel/i });
    const order = ["bottom-right", "bottom-left", "top-left", "top-right"];
    for (const expected of order) {
      fireEvent.click(moveBtn);
      expect(localStorage.getItem("stacky.activeRunsPanel.corner")).toBe(
        JSON.stringify(expected),
      );
    }
  });

  it("muestra un aviso inline cuando cancelar falla, sin ocultar el panel", async () => {
    mockRuns([RUN]);
    mockCancel.mockRejectedValueOnce(new Error("500 INTERNAL SERVER ERROR: boom"));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));

    await waitFor(() =>
      expect(screen.getByText(/No se pudo cancelar #42/i)).toBeDefined(),
    );
    // El panel sigue visible con el run listado.
    expect(screen.getByText("#42")).toBeDefined();
  });

  it("el botón Reintentar del aviso re-dispara la cancelación sin nuevo confirm", async () => {
    mockRuns([RUN]);
    mockCancel.mockRejectedValueOnce(new Error("timeout"));
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));
    await waitFor(() =>
      expect(screen.getByText(/No se pudo cancelar #42/i)).toBeDefined(),
    );

    confirmSpy.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /^reintentar$/i }));

    expect(confirmSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(mockCancel).toHaveBeenCalledTimes(2));
  });
});
