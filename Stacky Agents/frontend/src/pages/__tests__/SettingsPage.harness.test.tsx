/**
 * Tests de integración mínimos para el sub-tab "Arnes" en SettingsPage
 * (Plan 33 F2.2).
 *
 * Cubre:
 * 1. Click en "Arnes" → HarnessFlagsPanel visible.
 * 2. Click en otro tab → HarnessFlagsPanel ya no está en el DOM.
 *
 * NOTA: vitest no está instalado en este entorno (ver memoria backend-dev-test-env);
 * el archivo sigue la convención del repo y se ejecuta cuando el toolchain esté.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import type { ReactElement } from "react";
import SettingsPage from "../SettingsPage";

// ─── Mocks ────────────────────────────────────────────────────────────────────

// HarnessFlagsPanel hace una query de harness-flags al montar
vi.mock("../../api/endpoints", () => ({
  HarnessFlags: {
    list: vi.fn(async () => ({
      ok: true,
      flags: [
        {
          key: "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED",
          type: "bool",
          label: "Gate de contrato (claude)",
          description: "F1.1",
          group: "claude_code_cli",
          pair: null,
          env_only: false,
          value: false,
          category: "runtimes_cli",
          default: false,
          default_known: false,
          active: false,
        },
      ],
      active_profile: null,
      categories: [
        { id: "runtimes_cli", label: "Runtimes CLI (Claude / Codex)", description: "" },
      ],
    })),
    update: vi.fn(async () => ({ ok: true })),
  },
  Webhooks: {
    list: vi.fn(async () => []),
    create: vi.fn(),
    deactivate: vi.fn(),
    delete: vi.fn(),
  },
}));

// SettingsPage usa uiSectionsStore; stub mínimo
vi.mock("../../store/uiSectionsStore", () => ({
  useUiSectionsStore: () => ({
    sections: { pm: false, logs: false, docs: false, memory: false },
  }),
}));

vi.mock("../../services/uiSections", () => ({
  setSectionVisible: vi.fn(async () => {}),
  LOCKED_SECTIONS: ["team", "tickets", "settings"],
  OPTIONAL_SECTIONS: ["pm", "logs", "docs", "memory"],
}));

// FlowConfigPage y otros sub-panels pesados → stub liviano
vi.mock("../FlowConfigPage", () => ({ default: () => <div>FlowPanel</div> }));
vi.mock("../../components/ConfigTransferPanel", () => ({ default: () => <div>Transfer</div> }));
vi.mock("../../components/ClientProfileEditor", () => ({ default: () => <div>ClientProfile</div> }));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrap(ui: ReactElement) {
  return render(
    <QueryClientProvider client={makeQC()}>{ui}</QueryClientProvider>,
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("SettingsPage — sub-tab Arnes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("click en 'Arnes' muestra el HarnessFlagsPanel", async () => {
    wrap(<SettingsPage />);

    const arnesTab = screen.getByRole("button", { name: "Arnes" });
    fireEvent.click(arnesTab);

    // Esperar a que el panel cargue y muestre el label del flag
    await waitFor(() => {
      expect(screen.getByText("Gate de contrato (claude)")).toBeDefined();
    });
  });

  it("click en otro tab oculta el HarnessFlagsPanel", async () => {
    wrap(<SettingsPage />);

    // Navegar a Arnes primero
    fireEvent.click(screen.getByRole("button", { name: "Arnes" }));
    await waitFor(() => screen.getByText("Gate de contrato (claude)"));

    // Volver a Flujo
    fireEvent.click(screen.getByRole("button", { name: "Flujo" }));

    // El label del panel de arnés ya no debe estar en el DOM
    expect(screen.queryByText("Gate de contrato (claude)")).toBeNull();
  });
});
