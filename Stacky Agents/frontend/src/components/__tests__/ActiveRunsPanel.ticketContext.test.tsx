/**
 * Tests de componente para el contexto de ticket (proyecto/título) en la fila
 * de ActiveRunsPanel (plan 134 F7).
 *
 * Archivo SEPARADO de ActiveRunsPanel.test.tsx para no colisionar con las
 * ediciones del plan 132 en el mismo componente.
 *
 * NOTA DE ENTORNO: este archivo no puede ejecutarse en este checkout porque
 * faltan `@testing-library/react` y un entorno jsdom en node_modules/vitest
 * config (gap preexistente, no introducido por este cambio — se reproduce
 * igual en ActiveRunsPanel.test.tsx y en cualquier test de componente ya
 * existente, p.ej. WeeklyDigestCard.test.tsx). Queda listo para correr en
 * cuanto se resuelva ese gap de entorno.
 */

import { render, screen, waitFor, cleanup } from "@testing-library/react";
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

/** Responde según el status pedido: "running" trae el run de prueba, el resto vacío. */
function mockRuns(runs: AgentExecution[]) {
  mockList.mockImplementation(
    async (q: { status?: string }) => (q.status === "running" ? runs : []),
  );
}

describe("ActiveRunsPanel — contexto de ticket (plan 134 F7)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockCancel.mockResolvedValue({ ok: true, execution_id: 42 });
  });

  afterEach(() => {
    cleanup();
  });

  it("muestra proyecto y título del ticket cuando el backend los envía", async () => {
    const run: AgentExecution = {
      id: 42,
      ticket_id: 1001,
      agent_type: "developer",
      status: "running",
      input_context: [],
      chain_from: [],
      started_by: "operator",
      started_at: "2026-07-09T10:00:00Z",
      project: "proj-x",
      ticket_title: "Migrar login",
    };
    mockRuns([run]);
    wrap(<ActiveRunsPanel />);

    await waitFor(() =>
      expect(screen.getByText(/proj-x/)).toBeDefined(),
    );
    expect(screen.getByText(/Migrar login/)).toBeDefined();
  });

  it("degrada a 'ticket N' cuando el backend no envía contexto", async () => {
    const run: AgentExecution = {
      id: 43,
      ticket_id: 42,
      agent_type: "developer",
      status: "running",
      input_context: [],
      chain_from: [],
      started_by: "operator",
      started_at: "2026-07-09T10:00:00Z",
    };
    mockRuns([run]);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText(/ticket 42/)).toBeDefined());
    expect(screen.queryByText(/proj-x/)).toBeNull();
  });
});
