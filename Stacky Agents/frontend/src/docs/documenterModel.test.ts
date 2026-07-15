import { describe, it, expect } from "vitest";
import {
  summarizeDocumenterStatus,
  healthDelta,
  formatSkipReason,
  buildFilesView,
  buildSkippedView,
  buildRunsView,
} from "./documenterModel";
import type { DocumenterStatusResponse } from "../api/endpoints";

describe("summarizeDocumenterStatus", () => {
  it("summarizeDocumenterStatus_maps_states", () => {
    const running = summarizeDocumenterStatus({ ok: true, state: "running" });
    expect(running.uiState).toBe("running");
    expect(running.running).toBe(true);

    const done = summarizeDocumenterStatus({ ok: true, state: "completed" });
    expect(done.uiState).toBe("completed");

    const decided = summarizeDocumenterStatus({ ok: true, state: "decided_keep" });
    expect(decided.uiState).toBe("decided");

    const unknown = summarizeDocumenterStatus(null);
    expect(unknown.uiState).toBe("unknown");
  });

  it("summarizeDocumenterStatus_flags_degraded", () => {
    const s: DocumenterStatusResponse = {
      ok: true, state: "completed", degraded: true,
      written: ["a.md", "b.md"], skipped: [["c.md", "canonical_readonly"]],
      branch: null, diff_stat: "",
    };
    const sum = summarizeDocumenterStatus(s);
    expect(sum.degraded).toBe(true);
    expect(sum.writtenCount).toBe(2);
    expect(sum.skippedCount).toBe(1);
  });

  it("summarizeDocumenterStatus_exposes_current_execution_id", () => {
    // Fix "no me hizo nada" (Tarea 2) — necesario para enganchar la consola en vivo.
    const running = summarizeDocumenterStatus({
      ok: true, state: "running", current_execution_id: 123,
    });
    expect(running.currentExecutionId).toBe(123);

    const noExec = summarizeDocumenterStatus({ ok: true, state: "running" });
    expect(noExec.currentExecutionId).toBeNull();
  });

  it("summarizeDocumenterStatus_exposes_error_message", () => {
    // Fix "no me hizo nada" (Tarea 1) — antes era 100% silencioso.
    const failed = summarizeDocumenterStatus({
      ok: true, state: "completed", written: [], skipped: [],
      error: "ENRIQUECER: ejecución 42 terminó en 'error': config faltante",
    });
    expect(failed.errorMessage).toContain("config faltante");

    const ok = summarizeDocumenterStatus({ ok: true, state: "completed" });
    expect(ok.errorMessage).toBeNull();
  });
});

describe("healthDelta", () => {
  it("healthDelta_describes_improvement", () => {
    expect(healthDelta({ status: "SIN_DOCS" }, { status: "INCOMPLETA" })).toBe(
      "SIN_DOCS → INCOMPLETA"
    );
    expect(healthDelta({ status: "SANA" }, { status: "SANA" })).toContain("Sin cambio");
    expect(healthDelta(null, { status: "SANA" })).toBe("");
  });
});

// ---------------------------------------------------------------------------
// Plan 137 F6 — panel de revisión: preview, citas, saltados, historial.
// ---------------------------------------------------------------------------

describe("formatSkipReason", () => {
  it("formatSkipReason_mapea_claves_conocidas_prefijo_y_desconocida", () => {
    expect(formatSkipReason("unsafe_path")).toBe("Ruta insegura (fuera del repo)");
    expect(formatSkipReason("canonical_readonly")).toBe("docs/sistema/ es de solo lectura");
    expect(formatSkipReason("missing_confidence_marks")).toBe("Sin marcas [V]/[INF]/[NV]");
    expect(formatSkipReason("max_files_cap")).toBe("Superó el tope de archivos del run");
    expect(formatSkipReason("write_error:disk full")).toBe("Error de escritura");
    expect(formatSkipReason("algo_no_mapeado")).toBe("algo_no_mapeado");
  });
});

describe("buildFilesView", () => {
  it("buildFilesView_mapea_preview_y_citas", () => {
    const status: DocumenterStatusResponse = {
      ok: true,
      files: [
        {
          path: "docs/a.md", action: "create", content_preview: "hola",
          citations: { total: 3, ok: 2, bad: ["x.py:9"] },
        },
      ],
    };
    const view = buildFilesView(status);
    expect(view).toHaveLength(1);
    expect(view[0].path).toBe("docs/a.md");
    expect(view[0].preview).toBe("hola");
    expect(view[0].citationsLabel).toBe("2/3 citas verificadas");
    expect(view[0].citationsBad).toEqual(["x.py:9"]);
  });

  it("buildFilesView_sin_files_da_vacio", () => {
    expect(buildFilesView({ ok: true })).toEqual([]);
    expect(buildFilesView(null)).toEqual([]);
    expect(buildFilesView(undefined)).toEqual([]);
  });

  it("buildFilesView_sin_citations_da_label_vacio", () => {
    const view = buildFilesView({
      ok: true, files: [{ path: "a.md", action: "create" }],
    });
    expect(view[0].citationsLabel).toBe("");
    expect(view[0].citationsBad).toEqual([]);
    expect(view[0].preview).toBe("");
  });
});

describe("buildSkippedView", () => {
  it("buildSkippedView_traduce_razon", () => {
    const view = buildSkippedView({
      ok: true, skipped: [["a.md", "missing_confidence_marks"]],
    });
    expect(view).toEqual([{ path: "a.md", label: "Sin marcas [V]/[INF]/[NV]" }]);
  });

  it("buildSkippedView_sin_skipped_da_vacio", () => {
    expect(buildSkippedView({ ok: true })).toEqual([]);
    expect(buildSkippedView(null)).toEqual([]);
  });
});

describe("buildRunsView", () => {
  it("buildRunsView_mapea_historial_con_citas", () => {
    const rows = buildRunsView({
      ok: true,
      runs: [{
        run_id: "r1", state: "completed", branch: "stacky/doc-x",
        written_count: 2, skipped_count: 1, citations_ok: 3, citations_total: 4,
        mtime_iso: "2026-07-15T00:00:00Z",
      }],
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].runId).toBe("r1");
    expect(rows[0].countsLabel).toBe("2 escritos · 1 saltados");
    expect(rows[0].citationsLabel).toBe("citas 3/4");
  });

  it("buildRunsView_degradado_sin_rama", () => {
    const rows = buildRunsView({
      ok: true,
      runs: [{ run_id: "r2", state: "completed", written_count: 0, skipped_count: 0 }],
    });
    expect(rows[0].branch).toBe("(degradado)");
    expect(rows[0].citationsLabel).toBe("");
  });

  it("buildRunsView_entrada_invalida_da_vacio", () => {
    expect(buildRunsView(null)).toEqual([]);
    expect(buildRunsView({})).toEqual([]);
    expect(buildRunsView({ runs: "x" })).toEqual([]);
  });
});
