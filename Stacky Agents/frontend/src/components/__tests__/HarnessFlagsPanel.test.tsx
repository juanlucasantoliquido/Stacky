/**
 * Tests de componente para HarnessFlagsPanel (Plan 33 F1.2).
 *
 * Cubre:
 * 1. Renderiza grupos y labels del mock del registry.
 * 2. Toggle bool llama HarnessFlags.update con el valor correcto.
 * 3. JSON inválido bloquea el guardado (no llama update).
 * 4. Botón de perfil "safe" llama al endpoint de perfiles.
 * 5. Error de API muestra mensaje en línea sin crash.
 */

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import type { ReactElement } from "react";
import HarnessFlagsPanel from "../HarnessFlagsPanel";
import type { HarnessFlagView } from "../../api/endpoints";

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock("../../api/endpoints", () => ({
  HarnessFlags: {
    list: vi.fn(),
    update: vi.fn(),
  },
}));

import { HarnessFlags } from "../../api/endpoints";

const mockList = HarnessFlags.list as ReturnType<typeof vi.fn>;
const mockUpdate = HarnessFlags.update as ReturnType<typeof vi.fn>;

// fetch para applyProfile
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const BOOL_FLAG: HarnessFlagView = {
  key: "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED",
  type: "bool",
  label: "Gate de contrato (claude)",
  description: "F1.1 — Si ON, outputs con errores duros degradan el run.",
  group: "claude_code_cli",
  pair: null,
  env_only: false,
  value: false,
};

const JSON_FLAG: HarnessFlagView = {
  key: "STACKY_MEMORY_CAPS_JSON",
  type: "json",
  label: "Caps de memoria por agente (JSON)",
  description: "M0.1 — Override por agente.",
  group: "global",
  pair: null,
  env_only: false,
  value: "",
};

const BOOL_WITH_PAIR: HarnessFlagView = {
  key: "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED",
  type: "bool",
  label: "Conocimiento de proyecto (claude)",
  description: "F2.2 — Anti-patrones en el system prompt.",
  group: "claude_code_cli",
  pair: "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS",
  env_only: false,
  value: true,
};

const PAIR_CSV: HarnessFlagView = {
  key: "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS",
  type: "csv",
  label: "Proyectos — conocimiento",
  description: "Allowlist CSV de proyectos.",
  group: "claude_code_cli",
  pair: null,
  env_only: false,
  value: "RSPACIFICO",
};

// [Plan 78 C4+C7] categories con tier:"simple" para que los flags sean visibles
// en modo Simple (default). Sin tier, el flag caería al catch-all colapsado.
// Comentario-contrato: todo mock que monte HarnessFlagsPanel DEBE incluir al menos
// una categoría tier:"simple" con el flag que aseran; de lo contrario el test
// dependería del modo Experto, que no es el default.
const MOCK_RESPONSE = {
  ok: true,
  flags: [BOOL_FLAG, JSON_FLAG, BOOL_WITH_PAIR, PAIR_CSV],
  active_profile: "safe",
  categories: [
    {
      id: "claude_code_cli",
      label: "Claude Code CLI",
      description: "Flags del runtime Claude Code CLI",
      tier: "simple" as const,
      intent: "Elegir cómo y con qué modelo corren los agentes",
    },
    {
      id: "global",
      label: "Global",
      description: "Flags globales",
      tier: "simple" as const,
      intent: "Configuración global del arnés",
    },
  ],
};

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

describe("HarnessFlagsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue(MOCK_RESPONSE);
    mockUpdate.mockResolvedValue({ ok: true, applied: {} });
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, active_profile: "safe" }),
    });
  });

  it("renderiza grupos y labels del mock del registry", async () => {
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => {
      // Grupo global aparece
      expect(screen.getByText("Global")).toBeDefined();
      // Grupo claude
      expect(screen.getByText("Claude Code CLI")).toBeDefined();
      // Labels de flags
      expect(screen.getByText("Gate de contrato (claude)")).toBeDefined();
      expect(screen.getByText("Caps de memoria por agente (JSON)")).toBeDefined();
    });
  });

  it("toggle bool llama HarnessFlags.update con el valor correcto", async () => {
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => screen.getByText("Gate de contrato (claude)"));

    // El flag empieza en false, el checkbox está desmarcado
    // Buscamos el checkbox asociado al toggle del flag bool (sin pair)
    const checkboxes = screen.getAllByRole("checkbox");
    // El primer checkbox corresponde a BOOL_FLAG (value=false)
    const gateCheckbox = checkboxes[0];
    expect((gateCheckbox as HTMLInputElement).checked).toBe(false);

    fireEvent.click(gateCheckbox);

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith({
        CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED: true,
      });
    });
  });

  it("JSON inválido no llama update", async () => {
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => screen.getByText("Caps de memoria por agente (JSON)"));

    const textarea = screen.getByRole("textbox", {
      name: (_, el) => el.tagName === "TEXTAREA",
    }) as HTMLTextAreaElement | undefined
      ?? screen.getAllByRole("textbox").find(
        (el) => el.tagName === "TEXTAREA",
      ) as HTMLTextAreaElement;

    // Escribir JSON inválido
    fireEvent.change(textarea, { target: { value: "{ invalid json" } });
    fireEvent.blur(textarea);

    // No debe llamar a update
    expect(mockUpdate).not.toHaveBeenCalled();
    // Mensaje de error visible
    await waitFor(() => {
      expect(screen.getByText("JSON inválido")).toBeDefined();
    });
  });

  it("botón de perfil 'safe' llama al endpoint de perfiles", async () => {
    wrap(<HarnessFlagsPanel />);
    // [Plan 78 C7] El hero nuevo muestra "Perfil:" (no "Perfil activo:").
    await waitFor(() => screen.getByText(/Perfil:/i));

    const safeBtn = screen.getByRole("button", { name: "safe" });
    fireEvent.click(safeBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/harness-flags/profile",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("error de API muestra mensaje en línea sin crash", async () => {
    mockUpdate.mockRejectedValue(new Error("timeout de red"));

    wrap(<HarnessFlagsPanel />);
    await waitFor(() => screen.getByText("Gate de contrato (claude)"));

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);

    await waitFor(() => {
      expect(screen.getByText("timeout de red")).toBeDefined();
    });
  });
});
