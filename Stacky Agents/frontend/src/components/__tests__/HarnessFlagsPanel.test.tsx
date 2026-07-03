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
  category: "claude_code_cli",
  default: false,
  default_known: true,
  active: false,
  requires: null,
  requires_met: true,
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
  category: "global",
  default: "",
  default_known: false,
  active: false,
  requires: null,
  requires_met: true,
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
  category: "claude_code_cli",
  default: false,
  default_known: false,
  active: true,
  requires: null,
  requires_met: true,
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
  category: "claude_code_cli",
  default: "",
  default_known: false,
  active: true,
  requires: null,
  requires_met: true,
};

// ── Plan 82 — fixtures de dependencias master→hija, badge env, modificada ───
const MASTER_ENABLED: HarnessFlagView = {
  key: "STACKY_EXEC_VERIFICATION_ENABLED",
  type: "bool",
  label: "Verificación ejecutable",
  description: "Master de verificación ejecutable.",
  group: "global",
  pair: null,
  env_only: false,
  value: false,
  category: "global",
  default: false,
  default_known: false,
  active: false,
  requires: null,
  requires_met: true,
};

const CHILD_CONFIGURED_MASTER_OFF: HarnessFlagView = {
  key: "STACKY_EXEC_VERIFICATION_TIMEOUT_S",
  type: "int",
  label: "Timeout por verificador",
  description: "Timeout máximo por verificador individual.",
  group: "global",
  pair: null,
  env_only: false,
  value: 999,
  category: "global",
  default: 120,
  default_known: false,
  active: true,
  requires: "STACKY_EXEC_VERIFICATION_ENABLED",
  requires_met: false,
};

const CHILD_DEFAULT_MASTER_OFF: HarnessFlagView = {
  ...CHILD_CONFIGURED_MASTER_OFF,
  key: "STACKY_EXEC_VERIFICATION_BUDGET_S",
  label: "Budget de verificación",
  value: 0,
  active: false,
};

const CHILD_MASTER_ON: HarnessFlagView = {
  ...CHILD_CONFIGURED_MASTER_OFF,
  key: "STACKY_EXEC_REPAIR_MAX_RETRIES",
  label: "Max reintentos reparación",
  requires_met: true,
};

const ENV_ONLY_FLAG: HarnessFlagView = {
  key: "STACKY_ADO_EDIT_SWEEP_HOURS",
  type: "int",
  label: "Intervalo del sweep ADO",
  description: "Cada cuántas horas relee ediciones.",
  group: "global",
  pair: null,
  env_only: true,
  value: 6,
  category: "global",
  default: 6,
  default_known: false,
  active: true,
  requires: null,
  requires_met: true,
};

const NON_ENV_FLAG: HarnessFlagView = {
  ...ENV_ONLY_FLAG,
  key: "STACKY_NON_ENV_FLAG",
  label: "Flag no env_only",
  env_only: false,
};

const MODIFIED_BOOL: HarnessFlagView = {
  key: "STACKY_TASK_GATE_ENABLED",
  type: "bool",
  label: "Gate modificado",
  description: "Flag apartada de su default.",
  group: "global",
  pair: null,
  env_only: false,
  value: true,
  category: "global",
  default: false,
  default_known: true,
  active: true,
  requires: null,
  requires_met: true,
};

const UNMODIFIED_BOOL: HarnessFlagView = {
  ...MODIFIED_BOOL,
  key: "STACKY_UNMODIFIED_FLAG",
  label: "Gate sin modificar",
  value: false,
  active: false,
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

// ─── Plan 82 — dependencias master→hija, badge env, modificada ────────────────

describe("HarnessFlagsPanel — Plan 82 F2 (requires + env badge)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUpdate.mockResolvedValue({ ok: true, applied: {} });
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, active_profile: "safe" }),
    });
  });

  // test_shows_requires_note_when_master_off
  it("muestra 'Sin efecto: requiere' cuando la hija está configurada y el master está OFF", async () => {
    mockList.mockResolvedValue({
      ...MOCK_RESPONSE,
      flags: [MASTER_ENABLED, CHILD_CONFIGURED_MASTER_OFF],
    });
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => {
      expect(screen.getByText(/Sin efecto: requiere/)).toBeDefined();
    });
  });

  // test_hides_requires_note_when_master_on
  it("no muestra la nota cuando requires_met es true (master ON)", async () => {
    mockList.mockResolvedValue({
      ...MOCK_RESPONSE,
      flags: [MASTER_ENABLED, CHILD_MASTER_ON],
    });
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => screen.getByText(CHILD_MASTER_ON.label));
    expect(screen.queryByText(/Sin efecto: requiere/)).toBeNull();
  });

  // test_hides_requires_note_when_child_inactive
  it("no muestra la nota cuando la hija está en default (inactive) aunque el master esté OFF", async () => {
    mockList.mockResolvedValue({
      ...MOCK_RESPONSE,
      flags: [MASTER_ENABLED, CHILD_DEFAULT_MASTER_OFF],
    });
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => screen.getByText(CHILD_DEFAULT_MASTER_OFF.label));
    expect(screen.queryByText(/Sin efecto: requiere/)).toBeNull();
  });

  // test_child_control_stays_enabled_when_master_off
  it("el control de la hija NO se deshabilita aunque requires_met sea false", async () => {
    mockList.mockResolvedValue({
      ...MOCK_RESPONSE,
      flags: [MASTER_ENABLED, CHILD_CONFIGURED_MASTER_OFF],
    });
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => screen.getByText(CHILD_CONFIGURED_MASTER_OFF.label));
    const numInput = screen.getByDisplayValue(String(CHILD_CONFIGURED_MASTER_OFF.value));
    expect((numInput as HTMLInputElement).disabled).toBe(false);
  });

  // test_requires_note_locate_master_sets_search
  it("click en 'ver master' setea la búsqueda con la key del master", async () => {
    mockList.mockResolvedValue({
      ...MOCK_RESPONSE,
      flags: [MASTER_ENABLED, CHILD_CONFIGURED_MASTER_OFF],
    });
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => screen.getByText(/Sin efecto: requiere/));

    const locateBtn = screen.getByRole("button", { name: "ver master" });
    fireEvent.click(locateBtn);

    const searchInput = screen.getByPlaceholderText("Buscar flag...") as HTMLInputElement;
    await waitFor(() => {
      expect(searchInput.value).toBe(MASTER_ENABLED.key);
    });
  });

  // test_env_badge_rendered_for_env_only
  it("muestra el badge 'env' solo para flags con env_only=true", async () => {
    mockList.mockResolvedValue({
      ...MOCK_RESPONSE,
      flags: [ENV_ONLY_FLAG, NON_ENV_FLAG],
    });
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => screen.getByText(ENV_ONLY_FLAG.label));
    // Un solo badge "env" (para ENV_ONLY_FLAG), ninguno para NON_ENV_FLAG.
    expect(screen.getAllByText("env")).toHaveLength(1);
  });

  // test_flag_key_rendered_in_row
  it("muestra la key técnica exacta de la flag en la fila", async () => {
    mockList.mockResolvedValue({
      ...MOCK_RESPONSE,
      flags: [ENV_ONLY_FLAG],
    });
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => {
      expect(screen.getByText(ENV_ONLY_FLAG.key)).toBeDefined();
    });
  });
});

describe("HarnessFlagsPanel — Plan 82 F3 (modificada + contadores + filtro)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUpdate.mockResolvedValue({ ok: true, applied: {} });
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, active_profile: "safe" }),
    });
  });

  // test_section_meta_shows_modified_count
  it("el meta de sección muestra 'N modificadas' cuando hay flags fuera de default", async () => {
    mockList.mockResolvedValue({
      ...MOCK_RESPONSE,
      flags: [MODIFIED_BOOL, UNMODIFIED_BOOL],
    });
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => {
      expect(screen.getByText(/1 modificadas/)).toBeDefined();
    });
  });

  // test_hero_shows_out_of_default_total
  it("el hero muestra el total 'fuera de default'", async () => {
    mockList.mockResolvedValue({
      ...MOCK_RESPONSE,
      flags: [MODIFIED_BOOL, UNMODIFIED_BOOL],
    });
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => {
      expect(screen.getByText("fuera de default")).toBeDefined();
    });
  });

  // test_only_modified_filter_hides_default_flags
  it("el filtro 'Solo modificadas' oculta las flags en default", async () => {
    mockList.mockResolvedValue({
      ...MOCK_RESPONSE,
      flags: [MODIFIED_BOOL, UNMODIFIED_BOOL],
    });
    wrap(<HarnessFlagsPanel />);
    await waitFor(() => screen.getByText(UNMODIFIED_BOOL.label));

    const onlyModifiedCheckbox = screen.getByLabelText("Solo modificadas");
    fireEvent.click(onlyModifiedCheckbox);

    await waitFor(() => {
      expect(screen.queryByText(UNMODIFIED_BOOL.label)).toBeNull();
      expect(screen.getByText(MODIFIED_BOOL.label)).toBeDefined();
    });
  });
});
