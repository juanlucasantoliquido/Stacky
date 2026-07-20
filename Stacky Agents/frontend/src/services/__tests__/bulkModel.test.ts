// Plan 187 F2 (K5) — modelo puro del lote (runner secuencial, resumen, cap,
// armado 2 pasos, guard de Escape). Workers = funciones async fake; SIN fake timers.
import { describe, it, expect } from "vitest";
import {
  BULK_EXECUTION_ACTION_MAX,
  capExecutionBatch,
  createBulkRunner,
  nextArmed,
  shouldClearSelectionOnEscape,
  summarizeBulk,
  type BulkResult,
  type BulkWorker,
} from "../bulkModel";

describe("createBulkRunner", () => {
  it("runner_secuencial_en_orden", async () => {
    const runner = createBulkRunner();
    const order: number[] = [];
    const worker: BulkWorker = async (id) => {
      await Promise.resolve();
      order.push(id);
    };
    const r = await runner.run([1, 2, 3], worker)!;
    expect(order).toEqual([1, 2, 3]);
    expect(r).toEqual({ total: 3, ok: [1, 2, 3], failed: [] });
  });

  it("runner_fallo_no_corta_el_lote", async () => {
    const runner = createBulkRunner();
    const executed: number[] = [];
    const worker: BulkWorker = async (id) => {
      executed.push(id);
      if (id === 2) throw new Error("falla-b");
    };
    const r = await runner.run([1, 2, 3], worker)!;
    expect(r.ok).toEqual([1, 3]);
    expect(r.failed.map((f) => f.id)).toEqual([2]);
    expect(r.failed[0].error).toContain("falla-b");
    expect(executed).toContain(3);
  });

  it("runner_captura_throw_sincronico", async () => {
    const runner = createBulkRunner();
    const worker = (): Promise<void> => {
      throw new Error("boom");
    };
    const r = await runner.run([1], worker)!;
    expect(r.failed[0].error).toBe("boom");
  });

  it("runner_error_truncado_200", async () => {
    const runner = createBulkRunner();
    const long = "x".repeat(500);
    const worker: BulkWorker = async () => {
      throw new Error(long);
    };
    const r = await runner.run([1], worker)!;
    expect(r.failed[0].error.length).toBe(200);
  });

  it("runner_progreso_por_item", async () => {
    const runner = createBulkRunner();
    const calls: Array<[number, number]> = [];
    const worker: BulkWorker = async (id) => {
      if (id === 2) throw new Error("e");
    };
    await runner.run([1, 2, 3], worker, (d, t) => calls.push([d, t]))!;
    expect(calls).toEqual([
      [1, 3],
      [2, 3],
      [3, 3],
    ]);
  });

  it("runner_guard_doble_submit", async () => {
    const runner = createBulkRunner();
    let release!: () => void;
    const gate = new Promise<void>((res) => {
      release = res;
    });
    const slow: BulkWorker = () => gate;
    const p1 = runner.run([1], slow);
    expect(p1).not.toBeNull();
    const p2 = runner.run([2], slow);
    expect(p2).toBeNull(); // guard: ya hay un lote corriendo
    release();
    await p1;
    const p3 = runner.run([3], async () => {});
    expect(p3).not.toBeNull();
    await p3;
  });

  it("runner_dedup_ids", async () => {
    const runner = createBulkRunner();
    const seen: number[] = [];
    const worker: BulkWorker = async (id) => {
      seen.push(id);
    };
    const r = await runner.run([7, 7, 8], worker)!;
    expect(seen).toEqual([7, 8]);
    expect(r.total).toBe(2);
  });

  it("runner_ids_vacios", async () => {
    const runner = createBulkRunner();
    let called = false;
    const r = await runner.run([], async () => {
      called = true;
    })!;
    expect(r).toEqual({ total: 0, ok: [], failed: [] });
    expect(called).toBe(false);
  });
});

describe("capExecutionBatch (C5)", () => {
  it("cap_dentro_del_limite", () => {
    const within = Array.from({ length: BULK_EXECUTION_ACTION_MAX }, (_, i) => i);
    expect(capExecutionBatch(within)).toEqual({ ok: true });
    expect(capExecutionBatch([1])).toEqual({ ok: true });
  });

  it("cap_excedido_devuelve_toast", () => {
    const over = Array.from({ length: 26 }, (_, i) => i);
    const r = capExecutionBatch(over);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.toast.variant).toBe("warning");
      expect(r.toast.body).toContain("25");
      expect(r.toast.body).toContain("26");
    }
    // override de max
    const c = capExecutionBatch([1, 2, 3], 2);
    expect(c.ok).toBe(false);
    // dentro del override
    expect(capExecutionBatch([1, 2], 2)).toEqual({ ok: true });
  });
});

describe("summarizeBulk", () => {
  const mk = (ok: number[], failed: Array<{ id: number; error: string }>): BulkResult => ({
    total: ok.length + failed.length,
    ok,
    failed,
  });

  it("summarize_todo_ok_singular_y_plural", () => {
    const one = summarizeBulk(mk([1], []), "ejecución descartada", "ejecuciones descartadas");
    expect(one.variant).toBe("success");
    expect(one.body).toBe("1 ejecución descartada");
    const three = summarizeBulk(mk([1, 2, 3], []), "ejecución descartada", "ejecuciones descartadas");
    expect(three.variant).toBe("success");
    expect(three.body).toBe("3 ejecuciones descartadas");
  });

  it("summarize_parcial_lista_fallidos", () => {
    const r = summarizeBulk(
      mk([1, 2], [
        { id: 4, error: "e" },
        { id: 9, error: "e" },
      ]),
      "ejecución descartada",
      "ejecuciones descartadas",
    );
    expect(r.variant).toBe("warning");
    expect(r.title).toBe("Resultado parcial");
    expect(r.body).toContain("2 de 4 ejecuciones descartadas");
    expect(r.body).toContain("#4, #9");
  });

  it("summarize_mas_de_5_fallidos_trunca", () => {
    const failed = Array.from({ length: 7 }, (_, i) => ({ id: i + 1, error: "e" }));
    const r = summarizeBulk(mk([], failed), "ejecución descartada", "ejecuciones descartadas");
    expect(r.body).toContain("#1, #2, #3, #4, #5");
    expect(r.body).toContain("…");
    expect(r.body).not.toContain("#6");
  });

  it("summarize_todo_fallo", () => {
    const r = summarizeBulk(
      mk([], [{ id: 3, error: "kaboom" }]),
      "ejecución descartada",
      "ejecuciones descartadas",
    );
    expect(r.variant).toBe("error");
    expect(r.title).toBe("Falló el lote");
    expect(r.body).toContain("primer error:");
  });
});

describe("nextArmed", () => {
  it("nextArmed_arma_y_ejecuta", () => {
    expect(nextArmed(null, "discard")).toEqual({ armed: "discard", execute: false });
    expect(nextArmed("discard", "discard")).toEqual({ armed: null, execute: true });
    expect(nextArmed("discard", "delete")).toEqual({ armed: "delete", execute: false });
  });
});

describe("shouldClearSelectionOnEscape", () => {
  const esc = { key: "Escape" };

  it("escape_guard_true_fuera_de_inputs", () => {
    expect(shouldClearSelectionOnEscape(esc, null)).toBe(true);
    expect(shouldClearSelectionOnEscape(esc, { tagName: "TD", isContentEditable: false })).toBe(true);
    expect(
      shouldClearSelectionOnEscape(esc, {
        tagName: "INPUT",
        isContentEditable: false,
        type: "checkbox",
      }),
    ).toBe(true);
  });

  it("escape_guard_false_en_campos_de_texto", () => {
    expect(
      shouldClearSelectionOnEscape(esc, { tagName: "INPUT", isContentEditable: false, type: "text" }),
    ).toBe(false);
    expect(
      shouldClearSelectionOnEscape(esc, { tagName: "INPUT", isContentEditable: false, type: "search" }),
    ).toBe(false);
    expect(shouldClearSelectionOnEscape(esc, { tagName: "INPUT", isContentEditable: false })).toBe(false);
    expect(shouldClearSelectionOnEscape(esc, { tagName: "TEXTAREA", isContentEditable: false })).toBe(false);
    expect(shouldClearSelectionOnEscape(esc, { tagName: "SELECT", isContentEditable: false })).toBe(false);
    expect(shouldClearSelectionOnEscape(esc, { tagName: "DIV", isContentEditable: true })).toBe(false);
    // key distinta a Escape ⇒ false
    expect(shouldClearSelectionOnEscape({ key: "a" }, null)).toBe(false);
  });
});
