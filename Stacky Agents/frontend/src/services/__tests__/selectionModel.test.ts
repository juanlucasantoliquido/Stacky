// Plan 187 F1 (K4) — modelo puro de selección múltiple.
import { describe, it, expect } from "vitest";
import {
  EMPTY_SELECTION,
  clearSelection,
  clickSelect,
  headerState,
  pruneToKnown,
  rangeSelect,
  retainOnly,
  selectAllVisible,
  selectedIdsInOrder,
  toggleAllVisible,
  toggleOne,
  type SelectionState,
} from "../selectionModel";

const vis = [10, 20, 30, 40, 50];
const ids = (s: SelectionState) => [...s.selected].sort((a, b) => a - b);

describe("selectionModel (K4)", () => {
  it("toggle_selecciona_y_pone_ancla", () => {
    const s = toggleOne(EMPTY_SELECTION, 30);
    expect(ids(s)).toEqual([30]);
    expect(s.anchor).toBe(30);
  });

  it("toggle_deselecciona_y_mueve_ancla", () => {
    const s = toggleOne(toggleOne(EMPTY_SELECTION, 30), 30);
    expect(ids(s)).toEqual([]);
    expect(s.anchor).toBe(30);
  });

  it("rango_desde_ancla_hacia_abajo", () => {
    const s = rangeSelect(toggleOne(EMPTY_SELECTION, 20), 40, vis);
    expect(ids(s)).toEqual([20, 30, 40]);
    expect(s.anchor).toBe(20);
  });

  it("rango_invertido", () => {
    const s = rangeSelect(toggleOne(EMPTY_SELECTION, 40), 20, vis);
    expect(ids(s)).toEqual([20, 30, 40]);
  });

  it("rango_sin_ancla_equivale_a_toggle", () => {
    const s = rangeSelect(EMPTY_SELECTION, 30, vis);
    expect(ids(s)).toEqual([30]);
    expect(s.anchor).toBe(30);
  });

  it("rango_con_ancla_no_visible_equivale_a_toggle", () => {
    const base = toggleOne(EMPTY_SELECTION, 20); // anchor 20
    const s = rangeSelect(base, 40, [30, 40, 50]); // 20 no está ⇒ toggle 40
    expect(ids(s)).toEqual([20, 40]);
    expect(s.anchor).toBe(40);
  });

  it("rango_es_union_no_reemplazo", () => {
    let s = toggleOne(EMPTY_SELECTION, 10);
    s = toggleOne(s, 50);
    s = toggleOne(s, 20);
    s = rangeSelect(s, 30, vis);
    expect(ids(s)).toEqual([10, 20, 30, 50]);
  });

  it("clickSelect_prioriza_shift_sobre_ctrl", () => {
    const base = toggleOne(EMPTY_SELECTION, 20);
    const s = clickSelect(base, 40, vis, { shift: true, ctrl: true });
    expect(ids(s)).toEqual([20, 30, 40]); // semántica de rango
  });

  it("clickSelect_ctrl_es_toggle", () => {
    const s = clickSelect(EMPTY_SELECTION, 30, vis, { shift: false, ctrl: true });
    expect(ids(s)).toEqual([30]);
    expect(s.anchor).toBe(30);
  });

  it("selectAll_es_union_y_preserva_ancla", () => {
    const base = toggleOne(EMPTY_SELECTION, 20); // anchor 20
    const s = selectAllVisible(base, vis);
    expect(ids(s)).toEqual([10, 20, 30, 40, 50]);
    expect(s.anchor).toBe(20);
  });

  it("headerState_none_some_all", () => {
    expect(headerState(EMPTY_SELECTION, vis)).toBe("none");
    expect(headerState(toggleOne(EMPTY_SELECTION, 20), vis)).toBe("some");
    expect(headerState(selectAllVisible(EMPTY_SELECTION, vis), vis)).toBe("all");
    expect(headerState(EMPTY_SELECTION, [])).toBe("none");
  });

  it("toggleAll_desde_all_quita_solo_visibles", () => {
    // 5 visibles + un 99 no visible
    const withNonVisible = toggleOne(selectAllVisible(EMPTY_SELECTION, vis), 99);
    const s = toggleAllVisible(withNonVisible, vis);
    expect(ids(s)).toEqual([99]);
  });

  it("prune_elimina_ids_desaparecidos", () => {
    let s: SelectionState = { selected: new Set([20, 30]), anchor: 20 };
    s = pruneToKnown(s, [30, 40]);
    expect(ids(s)).toEqual([30]);
    expect(s.anchor).toBeNull();
  });

  it("retainOnly_conserva_fallidos", () => {
    const base: SelectionState = { selected: new Set([10, 20, 30]), anchor: 10 };
    const s = retainOnly(base, [20]);
    expect(ids(s)).toEqual([20]);
  });

  it("visibleIds_con_duplicados_no_rompen", () => {
    const dupVis = [10, 10, 20];
    const base = selectAllVisible(EMPTY_SELECTION, dupVis);
    expect(selectedIdsInOrder(base, dupVis)).toEqual([10, 20]); // sin duplicados
    expect(() => rangeSelect(toggleOne(EMPTY_SELECTION, 10), 20, dupVis)).not.toThrow();
  });

  it("clearSelection_vacia", () => {
    const s = clearSelection();
    expect(ids(s)).toEqual([]);
    expect(s.anchor).toBeNull();
  });

  it("inmutabilidad", () => {
    const original: SelectionState = { selected: new Set([10, 20]), anchor: 10 };
    const snapshot = [...original.selected];
    const results = [
      toggleOne(original, 30),
      rangeSelect(original, 40, vis),
      selectAllVisible(original, vis),
      toggleAllVisible(original, vis),
      pruneToKnown(original, [10]),
      retainOnly(original, [10]),
    ];
    // el Set original no fue mutado (referencia y contenido)
    expect([...original.selected]).toEqual(snapshot);
    // cada función devuelve un objeto de estado NUEVO
    for (const r of results) {
      expect(r).not.toBe(original);
      expect(r.selected).not.toBe(original.selected);
    }
  });
});
