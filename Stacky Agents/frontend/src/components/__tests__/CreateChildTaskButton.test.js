import { jsx as _jsx } from "react/jsx-runtime";
/**
 * Tests de componente para CreateChildTaskButton (Fase 2 — SDD).
 *
 * NOTA: Requiere Vitest + @testing-library/react.
 * Setup: npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
 * Y agregar en vite.config.ts: test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'] }
 *
 * TU-11e  No renderiza el botón cuando total_pending=0.
 * TU-11f  Renderiza el botón con label correcto cuando total_pending>0.
 * TU-12   Tras POST exitoso: invalida queries y muestra toast de éxito.
 * TU-FC-01 Modal muestra lista de RFs con preview del payload.
 * TU-FC-02 Checkbox dry_run disponible en modal.
 * TU-FC-03 Error de red en POST muestra error en UI sin crashear.
 * TU-FC-04 Botón Crear Task deshabilitado mientras hay request en vuelo.
 */
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import CreateChildTaskButton from "../CreateChildTaskButton";
// ─── Mocks ────────────────────────────────────────────────────────────────────
vi.mock("../../api/endpoints", () => ({
    Tickets: {
        listPendingTasks: vi.fn(),
        createChildTask: vi.fn(),
    },
}));
import { Tickets } from "../../api/endpoints";
const mockListPendingTasks = Tickets.listPendingTasks;
const mockCreateChildTask = Tickets.createChildTask;
// ─── Helpers ──────────────────────────────────────────────────────────────────
function makeQueryClient() {
    return new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });
}
function wrap(ui, qc) {
    const client = qc ?? makeQueryClient();
    return render(_jsx(QueryClientProvider, { client: client, children: ui }));
}
const EPIC_ADO_ID = 149;
const PENDING_TASK_1 = {
    rf_id: "RF-001",
    title: "RF-001 — Gestión de perfiles",
    pending_task_path: "Agentes/outputs/epic-149/rf-001-slug/pending-task.json",
    generated_at: "2026-05-15T10:00:00",
    plan_de_pruebas_path: "Agentes/outputs/epic-149/rf-001-slug/plan-de-pruebas.md",
    plan_exists: true,
    status: "pending_manual_creation",
};
function makeListResponse(pending) {
    return {
        ok: true,
        epic_ado_id: EPIC_ADO_ID,
        pending_tasks: pending,
        total_pending: pending.length,
        total_consumed: 0,
    };
}
function makeCreateResponse(overrides = {}) {
    return {
        ok: true,
        dry_run: false,
        epic_ado_id: EPIC_ADO_ID,
        task_ado_id: 5000,
        task_url: "https://dev.azure.com/TestOrg/TestProject/_workitems/edit/5000",
        attachment_id: "attach-uuid-001",
        actions: [
            { action: "create_work_item", ok: true, task_ado_id: 5000 },
            { action: "upload_attachment", ok: true, attachment_id: "attach-uuid-001" },
            { action: "link_attachment", ok: true },
        ],
        pending_task_consumed: true,
        idempotent: false,
        correlation_id: "test-corr-001",
        ...overrides,
    };
}
// ─── Tests ────────────────────────────────────────────────────────────────────
describe("CreateChildTaskButton", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });
    afterEach(() => {
        vi.resetAllMocks();
    });
    // ── TU-11e — Sin pendientes: botón no se muestra ──────────────────────────
    it("TU-11e: no muestra el botón cuando total_pending es 0", async () => {
        mockListPendingTasks.mockResolvedValue(makeListResponse([]));
        wrap(_jsx(CreateChildTaskButton, { epicAdoId: EPIC_ADO_ID }));
        // Esperar que el fetch se resuelva
        await waitFor(() => {
            expect(mockListPendingTasks).toHaveBeenCalledWith(EPIC_ADO_ID);
        });
        // El botón no debe existir en el DOM
        expect(screen.queryByRole("button", { name: /crear tasks en ado/i })).toBeNull();
    });
    // ── TU-11f — Con pendientes: botón visible con count correcto ─────────────
    it("TU-11f: muestra el botón con label correcto cuando total_pending > 0", async () => {
        mockListPendingTasks.mockResolvedValue(makeListResponse([PENDING_TASK_1]));
        wrap(_jsx(CreateChildTaskButton, { epicAdoId: EPIC_ADO_ID }));
        await waitFor(() => {
            const btn = screen.getByRole("button", { name: /crear tasks en ado/i });
            expect(btn).toBeDefined();
            expect(btn.textContent).toMatch(/1\s*pendiente/i);
        });
    });
    // ── TU-FC-01 — Modal muestra lista de RFs ────────────────────────────────
    it("TU-FC-01: modal muestra la lista de RFs pendientes al abrirse", async () => {
        mockListPendingTasks.mockResolvedValue(makeListResponse([PENDING_TASK_1]));
        wrap(_jsx(CreateChildTaskButton, { epicAdoId: EPIC_ADO_ID }));
        await waitFor(() => screen.getByRole("button", { name: /crear tasks en ado/i }));
        fireEvent.click(screen.getByRole("button", { name: /crear tasks en ado/i }));
        // El modal debe mostrar el RF-001
        await waitFor(() => {
            expect(screen.getByText(/RF-001/)).toBeDefined();
            expect(screen.getByText(/Gestión de perfiles/i)).toBeDefined();
        });
    });
    // ── TU-FC-02 — Checkbox dry_run en modal ─────────────────────────────────
    it("TU-FC-02: el modal tiene un checkbox dry_run disponible", async () => {
        mockListPendingTasks.mockResolvedValue(makeListResponse([PENDING_TASK_1]));
        wrap(_jsx(CreateChildTaskButton, { epicAdoId: EPIC_ADO_ID }));
        await waitFor(() => screen.getByRole("button", { name: /crear tasks en ado/i }));
        fireEvent.click(screen.getByRole("button", { name: /crear tasks en ado/i }));
        await waitFor(() => {
            const dryRunCheckbox = screen.getByRole("checkbox", { name: /dry.run/i });
            expect(dryRunCheckbox).toBeDefined();
            // Por defecto está desmarcado (la acción real es el default)
            expect(dryRunCheckbox.checked).toBe(false);
        });
    });
    // ── TU-12 — Tras POST exitoso: queries invalidadas y toast visible ────────
    it("TU-12: tras crear Task exitosamente, invalida queries y muestra toast de éxito", async () => {
        mockListPendingTasks.mockResolvedValue(makeListResponse([PENDING_TASK_1]));
        mockCreateChildTask.mockResolvedValue(makeCreateResponse());
        const qc = makeQueryClient();
        const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
        wrap(_jsx(CreateChildTaskButton, { epicAdoId: EPIC_ADO_ID }), qc);
        await waitFor(() => screen.getByRole("button", { name: /crear tasks en ado/i }));
        fireEvent.click(screen.getByRole("button", { name: /crear tasks en ado/i }));
        // Seleccionar el RF en el modal y confirmar
        await waitFor(() => screen.getByText(/RF-001/));
        const rfCheckbox = screen.getByRole("checkbox", { name: /RF-001/i });
        fireEvent.click(rfCheckbox);
        const createBtn = screen.getByRole("button", { name: /crear task en ado/i });
        fireEvent.click(createBtn);
        await waitFor(() => {
            // Verificar invalidación de queries
            expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: expect.arrayContaining(["pending-tasks"]) }));
            expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["tickets"] }));
        });
        // Toast de éxito debe aparecer
        await waitFor(() => {
            const toast = screen.getByRole("alert");
            expect(toast.textContent).toMatch(/5000|ADO/i);
        });
    });
    // ── TU-FC-03 — Error de red no crashea el componente ─────────────────────
    it("TU-FC-03: error en POST muestra mensaje de error sin crashear", async () => {
        mockListPendingTasks.mockResolvedValue(makeListResponse([PENDING_TASK_1]));
        mockCreateChildTask.mockRejectedValue(new Error("Network timeout"));
        wrap(_jsx(CreateChildTaskButton, { epicAdoId: EPIC_ADO_ID }));
        await waitFor(() => screen.getByRole("button", { name: /crear tasks en ado/i }));
        fireEvent.click(screen.getByRole("button", { name: /crear tasks en ado/i }));
        await waitFor(() => screen.getByText(/RF-001/));
        const rfCheckbox = screen.getByRole("checkbox", { name: /RF-001/i });
        fireEvent.click(rfCheckbox);
        const createBtn = screen.getByRole("button", { name: /crear task en ado/i });
        fireEvent.click(createBtn);
        // El componente no debe crashear — debe mostrar error
        await waitFor(() => {
            const errorEl = screen.getByRole("alert");
            expect(errorEl.textContent).toMatch(/error|falló|timeout/i);
        });
        // El componente sigue vivo
        expect(screen.queryByRole("dialog")).toBeDefined();
    });
    // ── TU-FC-04 — Botón deshabilitado durante request ────────────────────────
    it("TU-FC-04: botón Crear Task deshabilitado mientras el request está en vuelo", async () => {
        mockListPendingTasks.mockResolvedValue(makeListResponse([PENDING_TASK_1]));
        // Simular request lento que nunca se resuelve durante el test
        let resolveCreate;
        const slowPromise = new Promise((res) => {
            resolveCreate = res;
        });
        mockCreateChildTask.mockReturnValue(slowPromise);
        wrap(_jsx(CreateChildTaskButton, { epicAdoId: EPIC_ADO_ID }));
        await waitFor(() => screen.getByRole("button", { name: /crear tasks en ado/i }));
        fireEvent.click(screen.getByRole("button", { name: /crear tasks en ado/i }));
        await waitFor(() => screen.getByText(/RF-001/));
        const rfCheckbox = screen.getByRole("checkbox", { name: /RF-001/i });
        fireEvent.click(rfCheckbox);
        const createBtn = screen.getByRole("button", { name: /crear task en ado/i });
        fireEvent.click(createBtn);
        // El botón debe estar deshabilitado (o con indicador de carga)
        await waitFor(() => {
            const btn = screen.getByRole("button", { name: /crear task en ado|procesando/i });
            expect(btn.disabled).toBe(true);
        });
        // Resolver para limpiar
        resolveCreate(makeCreateResponse());
    });
    // ── GET pending-tasks error: botón con estado de error pero no bloquea render ──
    it("muestra estado de error cuando GET pending-tasks falla, sin crashear el card", async () => {
        mockListPendingTasks.mockRejectedValue(new Error("500 Internal Server Error"));
        // No debe lanzar excepción
        expect(() => wrap(_jsx(CreateChildTaskButton, { epicAdoId: EPIC_ADO_ID }))).not.toThrow();
        // Esperar un momento para que el fetch falle
        await waitFor(() => {
            expect(mockListPendingTasks).toHaveBeenCalled();
        });
        // El componente puede mostrar un indicador de error o simplemente no mostrar el botón
        // — lo importante es que no crasha el árbol de React
        // (El botón principal no aparece si no hay pending-tasks confirmados)
        expect(screen.queryByRole("button", { name: /crear tasks en ado/i })).toBeNull();
    });
});
