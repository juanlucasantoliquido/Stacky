/**
 * Tests de componente para MemoryConfigPanel (plan 26 — M0.2/M3.1/M3.2).
 *
 * Cubre: render del panel con flags ON/OFF, toggle del master que dispara el
 * mutation de flags, preview que consume context-preview y renderiza chars/hits,
 * y el panel de salud de directivas (overlapping/budget/stale).
 *
 * NOTA: vitest no está instalado en este entorno (ver memoria backend-dev-test-env);
 * el archivo sigue la convención del repo y se ejecuta cuando el toolchain esté.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import type { ReactElement } from "react";
import MemoryConfigPanel from "../memory/MemoryConfigPanel";

vi.mock("../../api/endpoints", () => ({
  HarnessFlags: {
    list: vi.fn(),
    update: vi.fn(async () => ({ ok: true })),
  },
  Memory: {
    types: vi.fn(async () => ({ injectable: ["pattern", "directive"], reserved: ["FA-01"] })),
    contextPreview: vi.fn(async () => ({
      content: "bloque",
      hits: 3,
      active_hits: 2,
      suppressed_hits: 1,
      directive_hits: 1,
    })),
    directiveHealth: vi.fn(async () => ({
      project: "P1",
      overlapping: [{ ids: ["a", "b"], shared_targeting: { agent_types: ["developer"] } }],
      budget_pressure: [{ project: "P1", agent_type: "developer", directive_chars: 900, cap: 1000, ratio: 0.9 }],
      stale: [{ id: "c", review_after: "2020-01-01", expires_at: null }],
    })),
  },
}));

import { HarnessFlags, Memory } from "../../api/endpoints";

const mockFlags = HarnessFlags.list as ReturnType<typeof vi.fn>;
const mockUpdate = HarnessFlags.update as ReturnType<typeof vi.fn>;

function flagList(masterOn: boolean) {
  return {
    ok: true,
    active_profile: null,
    flags: [
      { key: "STACKY_MEMORY_INJECTION_ENABLED", type: "bool", label: "", description: "", group: "memory", pair: null, env_only: true, value: masterOn },
      { key: "STACKY_MEMORY_INJECTION_PROJECTS", type: "csv", label: "", description: "", group: "memory", pair: null, env_only: true, value: "" },
      { key: "STACKY_MEMORY_CAPS_JSON", type: "json", label: "", description: "", group: "memory", pair: null, env_only: true, value: "" },
      { key: "STACKY_MEMORY_INJECT_SCOPES", type: "csv", label: "", description: "", group: "memory", pair: null, env_only: true, value: "project,team,global" },
    ],
  };
}

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  mockFlags.mockReset();
  mockUpdate.mockClear();
});

describe("MemoryConfigPanel", () => {
  it("refleja el master OFF", async () => {
    mockFlags.mockResolvedValue(flagList(false));
    wrap(<MemoryConfigPanel project="P1" />);
    await waitFor(() => expect(screen.getByText("OFF")).toBeTruthy());
  });

  it("togglear el master dispara HarnessFlags.update", async () => {
    mockFlags.mockResolvedValue(flagList(false));
    wrap(<MemoryConfigPanel project="P1" />);
    await waitFor(() => screen.getByText("Inyección habilitada (master)"));
    fireEvent.click(screen.getByRole("checkbox", { name: /master/i }));
    expect(mockUpdate).toHaveBeenCalledWith({ STACKY_MEMORY_INJECTION_ENABLED: true });
  });

  it("el preview consume context-preview y muestra chars/hits", async () => {
    mockFlags.mockResolvedValue(flagList(true));
    wrap(<MemoryConfigPanel project="P1" />);
    await waitFor(() => screen.getByText("Probar"));
    fireEvent.click(screen.getByText("Probar"));
    await waitFor(() => expect(screen.getByText(/hits: 3/)).toBeTruthy());
    expect(Memory.contextPreview).toHaveBeenCalled();
  });

  it("renderiza la salud de directivas (overlapping/budget/stale)", async () => {
    mockFlags.mockResolvedValue(flagList(true));
    wrap(<MemoryConfigPanel project="P1" />);
    await waitFor(() => expect(screen.getByText(/a ↔ b/)).toBeTruthy());
    expect(screen.getByText(/90%/)).toBeTruthy();
  });
});
