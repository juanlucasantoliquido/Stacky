// Plan 187 F1 — modelo puro de selección múltiple. Ids numéricos (los dos
// pilotos usan ids de ejecución number). Sin window, sin React, sin fetch.
// TODAS las funciones devuelven estado NUEVO, jamás mutan; `selected` es siempre
// un `Set` nuevo.
export type ItemId = number;

export interface SelectionState {
  selected: ReadonlySet<ItemId>;
  /** Ancla del rango Shift+click: el último id sobre el que se hizo click plano/ctrl. */
  anchor: ItemId | null;
}

export const EMPTY_SELECTION: SelectionState = { selected: new Set(), anchor: null };

export function isSelected(s: SelectionState, id: ItemId): boolean {
  return s.selected.has(id);
}

export function selectedCount(s: SelectionState): number {
  return s.selected.size;
}

/** Ids seleccionados EN EL ORDEN de visibleIds (determinismo del lote). Ignora
 *  duplicados de visibleIds (el primero gana) y seleccionados no visibles. */
export function selectedIdsInOrder(s: SelectionState, visibleIds: ItemId[]): ItemId[] {
  const seen = new Set<ItemId>();
  const out: ItemId[] = [];
  for (const id of visibleIds) {
    if (seen.has(id)) continue;
    seen.add(id);
    if (s.selected.has(id)) out.push(id);
  }
  return out;
}

/** Click plano o Ctrl/Cmd+click sobre el checkbox: toggle del id y el ancla pasa a
 *  ese id (tanto al seleccionar como al deseleccionar). */
export function toggleOne(s: SelectionState, id: ItemId): SelectionState {
  const next = new Set(s.selected);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return { selected: next, anchor: id };
}

/** (interno) devuelve los índices únicos deduplicados según el orden de visibleIds. */
function uniqueVisible(visibleIds: ItemId[]): ItemId[] {
  const seen = new Set<ItemId>();
  const out: ItemId[] = [];
  for (const id of visibleIds) {
    if (!seen.has(id)) {
      seen.add(id);
      out.push(id);
    }
  }
  return out;
}

/** Shift+click: UNIÓN de selected con el rango cerrado [anchor..id] según el orden
 *  de visibleIds. Si anchor es null o no está en visibleIds (o id no está visible)
 *  ⇒ equivale a toggleOne. El ancla NO cambia (comportamiento estándar de Shift+
 *  click). Funciona igual con id antes o después del ancla (min/max de índices). */
export function rangeSelect(
  s: SelectionState,
  id: ItemId,
  visibleIds: ItemId[],
): SelectionState {
  const ai = s.anchor == null ? -1 : visibleIds.indexOf(s.anchor);
  const ii = visibleIds.indexOf(id);
  if (ai === -1 || ii === -1) return toggleOne(s, id);
  const lo = Math.min(ai, ii);
  const hi = Math.max(ai, ii);
  const next = new Set(s.selected);
  for (let i = lo; i <= hi; i++) next.add(visibleIds[i]);
  return { selected: next, anchor: s.anchor };
}

/** Punto de entrada ÚNICO para el click de un checkbox de fila:
 *  shift ⇒ rangeSelect (ctrl se ignora si vienen ambos); si no ⇒ toggleOne. */
export function clickSelect(
  s: SelectionState,
  id: ItemId,
  visibleIds: ItemId[],
  mods: { shift: boolean; ctrl: boolean },
): SelectionState {
  if (mods.shift) return rangeSelect(s, id, visibleIds);
  return toggleOne(s, id);
}

/** Unión con todos los visibles; el ancla no cambia. */
export function selectAllVisible(s: SelectionState, visibleIds: ItemId[]): SelectionState {
  const next = new Set(s.selected);
  for (const id of visibleIds) next.add(id);
  return { selected: next, anchor: s.anchor };
}

/** Estado del checkbox de cabecera: visibleIds vacío ⇒ "none"; todos los visibles
 *  seleccionados ⇒ "all"; alguno pero no todos ⇒ "some". Los seleccionados NO
 *  visibles no cuentan para este cálculo. */
export function headerState(
  s: SelectionState,
  visibleIds: ItemId[],
): "none" | "some" | "all" {
  const uniq = uniqueVisible(visibleIds);
  if (uniq.length === 0) return "none";
  let count = 0;
  for (const id of uniq) if (s.selected.has(id)) count++;
  if (count === 0) return "none";
  if (count === uniq.length) return "all";
  return "some";
}

/** Click en la cabecera: headerState === "all" ⇒ quita los visibles del set (los no
 *  visibles, si los hubiera, se conservan); si no ⇒ selectAllVisible. */
export function toggleAllVisible(s: SelectionState, visibleIds: ItemId[]): SelectionState {
  if (headerState(s, visibleIds) === "all") {
    const next = new Set(s.selected);
    for (const id of visibleIds) next.delete(id);
    return { selected: next, anchor: s.anchor };
  }
  return selectAllVisible(s, visibleIds);
}

/** Escape / botón Deseleccionar. Devuelve un estado nuevo equivalente a EMPTY_SELECTION. */
export function clearSelection(): SelectionState {
  return { selected: new Set(), anchor: null };
}

/** Invariante ante refetch/cambio de página/filtro: selected ∩ knownIds; el ancla
 *  se conserva SOLO si sigue en knownIds (si no ⇒ null). */
export function pruneToKnown(s: SelectionState, knownIds: ItemId[]): SelectionState {
  const known = new Set(knownIds);
  const next = new Set<ItemId>();
  for (const id of s.selected) if (known.has(id)) next.add(id);
  const anchor = s.anchor != null && known.has(s.anchor) ? s.anchor : null;
  return { selected: next, anchor };
}

/** Tras un lote: conservar seleccionados SOLO los ids dados (los fallidos, para
 *  reintentar). Ancla: misma regla que pruneToKnown. */
export function retainOnly(s: SelectionState, ids: ItemId[]): SelectionState {
  const keep = new Set(ids);
  const next = new Set<ItemId>();
  for (const id of s.selected) if (keep.has(id)) next.add(id);
  const anchor = s.anchor != null && keep.has(s.anchor) ? s.anchor : null;
  return { selected: next, anchor };
}
