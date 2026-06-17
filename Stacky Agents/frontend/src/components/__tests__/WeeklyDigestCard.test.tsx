/**
 * Tests de componente para WeeklyDigestCard (U1.5 — doc 23).
 *
 * Cubre: preview de totals, highlights, botones de descarga MD/HTML con el
 * fmt correcto, badge "incluye estimados" (partial) y empty-state sin actividad.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import type { ReactElement } from "react";
import WeeklyDigestCard from "../WeeklyDigestCard";
import type { DigestReport } from "../../api/endpoints";

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock("../../api/endpoints", () => ({
  Reports: {
    digest: vi.fn(),
    digestDownloadUrl: vi.fn(
      (p: { fmt: string; days?: number }) =>
        `/api/reports/digest?fmt=${p.fmt}&days=${p.days ?? 7}`,
    ),
  },
}));

import { Reports } from "../../api/endpoints";

const mockDigest = Reports.digest as ReturnType<typeof vi.fn>;

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

const POPULATED: DigestReport = {
  period: { days: 7, start: "2026-06-06T00:00:00Z", end: "2026-06-13T00:00:00Z" },
  totals: {
    runs: 12,
    completed: 9,
    needs_review: 2,
    error: 1,
    success_rate: 0.75,
    tickets_touched: 5,
    cost_usd: { reported: 1.5, estimated: 0.5, total: 2.0 },
  },
  by_agent_type: [],
  by_runtime: [],
  top_failures: [{ kind: "timeout", count: 1 }],
  highlights: [
    "mejor agente: functional (90% éxito)",
    "runtime más usado: claude (8 runs)",
  ],
  partial: true,
};

const EMPTY: DigestReport = {
  period: { days: 7, start: "2026-06-06T00:00:00Z", end: "2026-06-13T00:00:00Z" },
  totals: {
    runs: 0,
    completed: 0,
    needs_review: 0,
    error: 0,
    success_rate: 0,
    tickets_touched: 0,
    cost_usd: { reported: 0, estimated: 0, total: 0 },
  },
  by_agent_type: [],
  by_runtime: [],
  top_failures: [],
  highlights: ["sin actividad en el período"],
  partial: false,
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("WeeklyDigestCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (Reports.digestDownloadUrl as ReturnType<typeof vi.fn>).mockImplementation(
      (p: { fmt: string; days?: number }) =>
        `/api/reports/digest?fmt=${p.fmt}&days=${p.days ?? 7}`,
    );
  });

  it("renderiza el preview de totals cuando hay actividad", async () => {
    mockDigest.mockResolvedValue(POPULATED);
    wrap(<WeeklyDigestCard />);
    await waitFor(() => {
      expect(screen.getByText("12")).toBeDefined();      // runs
      expect(screen.getByText("75%")).toBeDefined();     // success rate
      expect(screen.getByText("$2.00")).toBeDefined();   // costo total
      expect(screen.getByText("5")).toBeDefined();       // tickets tocados
    });
  });

  it("muestra los highlights del digest", async () => {
    mockDigest.mockResolvedValue(POPULATED);
    wrap(<WeeklyDigestCard />);
    await waitFor(() => {
      expect(screen.getByText(/mejor agente: functional/i)).toBeDefined();
      expect(screen.getByText(/runtime más usado: claude/i)).toBeDefined();
    });
  });

  it("expone botones de descarga MD y HTML con el fmt correcto", async () => {
    mockDigest.mockResolvedValue(POPULATED);
    wrap(<WeeklyDigestCard />);
    await waitFor(() => screen.getByText("12"));
    const md = screen.getByRole("link", { name: /MD/i });
    const html = screen.getByRole("link", { name: /HTML/i });
    expect(md.getAttribute("href")).toContain("fmt=md");
    expect(html.getAttribute("href")).toContain("fmt=html");
  });

  it("muestra el badge 'incluye estimados' cuando el digest es parcial", async () => {
    mockDigest.mockResolvedValue(POPULATED);
    wrap(<WeeklyDigestCard />);
    await waitFor(() => {
      expect(screen.getByText(/incluye estimados/i)).toBeDefined();
    });
  });

  it("muestra 'sin actividad' y conserva los botones cuando no hay runs", async () => {
    mockDigest.mockResolvedValue(EMPTY);
    wrap(<WeeklyDigestCard />);
    await waitFor(() => {
      expect(screen.getByText(/sin actividad/i)).toBeDefined();
    });
    // los botones de descarga siguen presentes (no crash, descarga igual disponible)
    expect(screen.getByRole("link", { name: /MD/i })).toBeDefined();
    expect(screen.getByRole("link", { name: /HTML/i })).toBeDefined();
  });
});
