import { describe, it, expect } from "vitest";
import {
  summarizeDocumenterStatus,
  healthDelta,
  formatSkipReason,
  buildFilesView,
  buildSkippedView,
  buildRunsView,
  normalizeOperatorNote,
  buildStagesView,
  buildVerdictView,
  buildRadiographyView,
  buildCorpusView,
  buildTriageView,
  formatTriageReason,
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

// ===========================================================================
// Plan 284 F2 - normalizacion de la nota del operador
// ===========================================================================

describe("Plan 284 - normalizeOperatorNote", () => {
  it("test_plan284_normalizeOperatorNote", () => {
    // Vacio o solo espacios => undefined: el body queda igual al de hoy.
    expect(normalizeOperatorNote("")).toBeUndefined();
    expect(normalizeOperatorNote("   ")).toBeUndefined();
    // Recorta los bordes.
    expect(normalizeOperatorNote("  hola  ")).toBe("hola");
    // Trunca al tope sin romper.
    const larga = "x".repeat(5000);
    expect(normalizeOperatorNote(larga)?.length).toBe(4000);
    // El tope es parametrizable (viaja desde el backend).
    expect(normalizeOperatorNote(larga, 10)?.length).toBe(10);
  });
});

// ===========================================================================
// Plan 284 F7 - la salida se entiende
// ===========================================================================

describe("Plan 284 - vistas del panel", () => {
  it("test_plan284_buildStagesView_orden_y_relleno", () => {
    const status = {
      stages: [
        { stage: "PROPONER", state: "done", summary: "1200 caracteres" },
        { stage: "CRITICAR", state: "skipped", summary: "sin plan que criticar" },
      ],
    } as DocumenterStatusResponse;

    const filas = buildStagesView(status);
    // Siempre 5 filas, en el orden canonico.
    expect(filas.length).toBe(5);
    expect(filas.map((f) => f.stage)).toEqual([
      "PROPONER", "CRITICAR", "MEJORAR", "IMPLEMENTAR", "VERIFICAR",
    ]);
    // Las que llegaron traen su estado real...
    expect(filas[0].state).toBe("done");
    expect(filas[0].badge).toBe("Hecha");
    expect(filas[1].badge).toBe("Salteada");
    // ...y las 3 que no corrieron quedan en pending.
    expect(filas.slice(2).every((f) => f.state === "pending")).toBe(true);
    expect(filas[4].badge).toBe("Pendiente");

    // Sin status: igual 5 filas (la UI nunca se rompe).
    expect(buildStagesView(null).length).toBe(5);
  });

  it("test_plan284_buildVerdictView_tabla", () => {
    const v = (verdict?: string) =>
      buildVerdictView({ verdict } as DocumenterStatusResponse);

    expect(v("RADIOGRAFIA_COMPLETA").label).toBe("Radiografía completa");
    expect(v("RADIOGRAFIA_COMPLETA").tone).toBe("ok");

    expect(v("RADIOGRAFIA_PARCIAL").label).toBe("Radiografía parcial");
    expect(v("RADIOGRAFIA_PARCIAL").tone).toBe("warn");

    expect(v("INSUFICIENTE").label).toBe("Insuficiente: revisá los rechazos");
    expect(v("INSUFICIENTE").tone).toBe("bad");

    expect(v("").label).toBe("Sin veredicto");
    expect(v("").tone).toBe("warn");
    expect(buildVerdictView(null).label).toBe("Sin veredicto");

    // La parada human-in-the-loop tambien tiene su etiqueta.
    expect(v("PENDIENTE_DE_APROBACION").label).toBe("Esperando tu aprobación");
  });

  it("test_plan284_buildRadiographyView_labels", () => {
    const conCobertura = buildRadiographyView({
      radiography: { modules_total: 15, modules_covered: 12, coverage_ratio: 0.8 },
      ticket_mining: { enabled: true, total: 228, signal: 96, noise: 132 },
      radiography_delta: { has_previous: true, ratio_delta: 0.12, modules_closed: ["a", "b", "c"] },
    } as DocumenterStatusResponse);
    expect(conCobertura.coverageLabel).toBe("Cobertura 12 de 15 módulos (80%)");
    expect(conCobertura.ticketsLabel).toBe(
      "228 tickets barridos — 96 aportaron historia, 132 descartados"
    );
    expect(conCobertura.deltaLabel).toBe("+12 pts desde el run anterior — cerraste 3 módulo(s)");

    const sinModulos = buildRadiographyView({
      radiography: { modules_total: 0 },
      ticket_mining: { enabled: false },
    } as DocumenterStatusResponse);
    expect(sinModulos.coverageLabel).toBe("Sin módulos que cubrir");
    expect(sinModulos.ticketsLabel).toBe("Minería de tickets desactivada");
    // Sin run previo no se muestra nada (degradacion silenciosa).
    expect(sinModulos.deltaLabel).toBe("");
  });

  it("test_plan284_formatSkipReason_citas", () => {
    // La razon nueva se traduce con su detalle.
    expect(formatSkipReason("citations_below_threshold:2/9")).toBe(
      "Rechazado: citas archivo:línea que no existen (2/9 verificadas)"
    );
    // PRESENCIA DE CONTROL: no rompimos el mapeo del 137.
    expect(formatSkipReason("canonical_readonly")).toBe(
      "docs/sistema/ es de solo lectura"
    );
    expect(formatSkipReason("unsafe_path")).toBe("Ruta insegura (fuera del repo)");
  });
});

describe("Plan 284 - awaiting_approval es un estado de UI de primera clase", () => {
  it("test_plan284_awaiting_approval_no_cae_en_unknown", () => {
    // El panel se renderiza con la condicion uiState !== "running" && !== "unknown".
    // Si awaiting_approval cayera en "unknown", los botones "Aprobar e
    // implementar"/"Cancelar" existirian pero NADIE los veria nunca: el patron
    // exacto de codigo construido, testeado y jamas cableado.
    const s = summarizeDocumenterStatus({ state: "awaiting_approval" } as DocumenterStatusResponse);
    expect(s.uiState).toBe("awaiting_approval");
    expect(s.uiState).not.toBe("unknown");
    expect(s.running).toBe(false);

    // budget_exhausted (A1) tampoco puede quedar invisible.
    const b = summarizeDocumenterStatus({ state: "budget_exhausted" } as DocumenterStatusResponse);
    expect(b.uiState).not.toBe("unknown");

    // PRESENCIA DE CONTROL: un estado desconocido de verdad SIGUE siendo unknown.
    const u = summarizeDocumenterStatus({ state: "vaya_a_saber" } as DocumenterStatusResponse);
    expect(u.uiState).toBe("unknown");
  });
});

// ---------------------------------------------------------------------------
// Plan 285 F1.2 — estado del corpus
// ---------------------------------------------------------------------------

describe("Plan 285 F1.2 — buildCorpusView", () => {
  it("corpus undefined: no se renderiza nada (backend viejo)", () => {
    expect(buildCorpusView(undefined).visible).toBe(false);
    expect(buildCorpusView(null).visible).toBe(false);
  });

  it("corpus vacio: avisa que el Documentador no tiene que consultar", () => {
    const v = buildCorpusView({ enabled: true, chunks_indexed: 0, files_scanned: 0 });
    expect(v.visible).toBe(true);
    expect(v.tone).toBe("warn");
    expect(v.label).toContain("Corpus vacío");
  });

  it("corpus con error: muestra el motivo en llano", () => {
    const v = buildCorpusView({ enabled: true, error: "sin_workspace_root" });
    expect(v.tone).toBe("warn");
    expect(v.label).toContain("carpeta de trabajo");
    // El error crudo desconocido NUNCA se oculta.
    const otro = buildCorpusView({ enabled: true, error: "disco lleno" });
    expect(otro.label).toContain("disco lleno");
  });

  it("corpus sano: los numeros salen del DATO, no de un literal", () => {
    const v = buildCorpusView({
      enabled: true, chunks_indexed: 94, files_scanned: 15, skipped_plans: 241,
    });
    expect(v.tone).toBe("ok");
    expect(v.label).toContain("94");
    expect(v.label).toContain("15");
    expect(v.label).toContain("241");
    // GEMELO: con otros numeros el texto cambia (si estuviera hardcodeado, no).
    const w = buildCorpusView({
      enabled: true, chunks_indexed: 7, files_scanned: 2, skipped_plans: 0,
    });
    expect(w.label).toContain("7");
    expect(w.label).not.toContain("94");
  });

  it("flag apagada: se ve el aviso, no se finge que esta sano", () => {
    const v = buildCorpusView({ enabled: false, chunks_indexed: 0 });
    expect(v.visible).toBe(true);
    expect(v.tone).toBe("warn");
  });
});

// ---------------------------------------------------------------------------
// Plan 285 F3.3 — descarte de tickets trazable
// ---------------------------------------------------------------------------

describe("Plan 285 F3.3 — buildTriageView", () => {
  const conMuestra = {
    enabled: true, total: 228, signal: 30, noise: 198, total_rows: 228,
    truncated: false,
    reason_counts: { sin_descripcion: 112, titulo_ruido: 8, motivo_nuevo_del_futuro: 3 },
    noise_sample: [
      { external_id: -7, tracker_type: "demo", title: "test", score: -8,
        reasons: ["sin_descripcion", "ticket_interno_de_stacky"] },
    ],
  };

  it("undefined o vacio: no se renderiza", () => {
    expect(buildTriageView(undefined).visible).toBe(false);
    expect(buildTriageView(null).visible).toBe(false);
    expect(buildTriageView({ enabled: true, total: 0 }).visible).toBe(false);
  });

  it("con datos: titular, motivos ordenados por frecuencia y filas", () => {
    const v = buildTriageView(conMuestra);
    expect(v.visible).toBe(true);
    expect(v.headline).toContain("198");
    expect(v.headline).toContain("228");
    // Ordenado por cantidad descendente.
    expect(v.reasonRows[0].reason).toBe("sin_descripcion");
    expect(v.reasonRows[0].count).toBe(112);
    expect(v.reasonRows[0].human).toBe("Sin descripción");
    expect(v.noiseRows[0].id).toBe("-7");
    expect(v.noiseRows[0].reasons).toContain("Ticket interno de Stacky (id negativo)");
    // AUSENCIA con GEMELO: sin truncar no hay aviso, pero si hay titular.
    expect(v.truncatedWarning).toBe("");
    expect(v.headline).not.toBe("");
  });

  it("truncado: el aviso dice cuantos faltaron", () => {
    const v = buildTriageView({ ...conMuestra, truncated: true, total: 500, total_rows: 900 });
    expect(v.truncatedWarning).toContain("500");
    expect(v.truncatedWarning).toContain("900");
    expect(v.truncatedWarning).toContain("NO es total");
  });

  it("motivo desconocido: nunca se pierde, se muestra el string crudo", () => {
    const v = buildTriageView(conMuestra);
    const desconocido = v.reasonRows.find((r) => r.reason === "motivo_nuevo_del_futuro");
    expect(desconocido).toBeDefined();
    expect(desconocido!.human).toBe("motivo_nuevo_del_futuro");
    // Y el mapeo por PREFIJO funciona con el dato pegado.
    expect(formatTriageReason("descripcion_extensa:900")).toBe("Descripción extensa");
  });
});
