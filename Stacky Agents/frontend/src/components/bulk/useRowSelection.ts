/**
 * Plan 187 F3 — hook que cablea selección/poda/Escape a cualquier página con lista.
 *
 * Toda la semántica pura vive en selectionModel/bulkModel (F1/F2); este hook solo
 * conecta estado React + eventos de DOM. Escape queda LOCAL por decisión de serie
 * (197 §6.4): NO migra al registry del 172 — su guard permite foco en checkbox y
 * su gating por `escapeDisabled` no lo replica el supresor global.
 */
import { useEffect, useState } from "react";
import {
  EMPTY_SELECTION,
  clearSelection,
  clickSelect,
  headerState,
  isSelected,
  pruneToKnown,
  retainOnly,
  selectedCount,
  selectedIdsInOrder,
  toggleAllVisible,
  type SelectionState,
} from "../../services/selectionModel";
import { shouldClearSelectionOnEscape } from "../../services/bulkModel";

export interface UseRowSelectionOptions {
  /** ids en orden visual — el caller los MEMOIZA (useMemo). */
  visibleIds: number[];
  /** flag ON; false ⇒ el hook es inerte (count 0, no-ops). */
  enabled: boolean;
  /** true mientras un drawer propio está abierto o corre un lote. */
  escapeDisabled?: boolean;
}

export interface UseRowSelectionResult {
  selection: SelectionState;
  /** C1 — retención post-lote: aplica retainOnly de forma FUNCIONAL (sin snapshot
   *  stale). setSelection crudo NO se expone (footgun de closure stale eliminado). */
  retainFailed: (failedIds: number[]) => void;
  count: number;
  header: "none" | "some" | "all";
  isRowSelected: (id: number) => boolean;
  orderedSelectedIds: number[];
  onRowCheckboxClick: (
    id: number,
    ev: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; stopPropagation(): void },
  ) => void;
  onToggleAll: () => void;
  clear: () => void;
}

export function useRowSelection(opts: UseRowSelectionOptions): UseRowSelectionResult {
  const { visibleIds, enabled, escapeDisabled } = opts;
  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);

  // Clave de dependencia barata sobre el array memoizado del caller.
  const visKey = visibleIds.join(",");

  // Poda (invariante §3.6): ante cambio de la lista cargada, selected ∩ visibleIds.
  useEffect(() => {
    setSelection((s) => pruneToKnown(s, visibleIds));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visKey]);

  const count = enabled ? selectedCount(selection) : 0;

  // Escape global: activo SOLO con selección y sin drawer/lote. Guard de foco propio
  // (shouldClearSelectionOnEscape): un checkbox NO bloquea; campos de texto SÍ.
  useEffect(() => {
    if (!enabled || count === 0 || escapeDisabled) return;
    const onKey = (ev: KeyboardEvent) => {
      const el = document.activeElement as HTMLInputElement | null;
      const active = el
        ? { tagName: el.tagName, isContentEditable: el.isContentEditable, type: el.type }
        : null;
      if (shouldClearSelectionOnEscape(ev, active)) {
        setSelection(clearSelection());
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [enabled, count, escapeDisabled]);

  if (!enabled) {
    return {
      selection: EMPTY_SELECTION,
      retainFailed: () => {},
      count: 0,
      header: "none",
      isRowSelected: () => false,
      orderedSelectedIds: [],
      onRowCheckboxClick: () => {},
      onToggleAll: () => {},
      clear: () => {},
    };
  }

  return {
    selection,
    retainFailed: (failedIds) => setSelection((s) => retainOnly(s, failedIds)),
    count,
    header: headerState(selection, visibleIds),
    isRowSelected: (id) => isSelected(selection, id),
    orderedSelectedIds: selectedIdsInOrder(selection, visibleIds),
    onRowCheckboxClick: (id, ev) => {
      ev.stopPropagation(); // crítico en Historial: la fila abre el drawer
      if (ev.shiftKey) window.getSelection()?.removeAllRanges();
      setSelection((s) =>
        clickSelect(s, id, visibleIds, { shift: ev.shiftKey, ctrl: ev.ctrlKey || ev.metaKey }),
      );
    },
    onToggleAll: () => setSelection((s) => toggleAllVisible(s, visibleIds)),
    clear: () => setSelection(clearSelection()),
  };
}
