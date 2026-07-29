// Plan 212 F4 — Qué modelos y efforts se OFRECEN al lanzar un agente. PURO.
//
// Vive aparte de modelEffortModel.ts (F7), que responde otra pregunta: qué pasó
// DESPUÉS de correr (solicitado vs efectivo).
//
// La regla que define este módulo: **ningún effort se esconde ni se deshabilita**.
// El operador quiere ver todos y decidir; lo que no soporta el modelo elegido se
// muestra ANOTADO con a qué degrada. Ocultarlos haría creer que no existen, y
// deshabilitarlos, que están rotos.

import type { RuntimeModelCatalog } from "../api/endpoints";

export interface EffortOption {
  id: string;
  label: string;
  supported: boolean;
  /** Lo que realmente se va a aplicar (puede diferir si degrada). */
  effective: string;
  /** Vacío si es soportado; si no, explica la degradación. */
  note: string;
}

export function buildEffortOptions(
  runtimeCatalog: RuntimeModelCatalog | undefined,
  modelId: string | null,
): EffortOption[] {
  const efforts = runtimeCatalog?.efforts ?? [];
  return efforts.map((e) => {
    const soporte = modelId ? runtimeCatalog?.effort_support?.[modelId] : undefined;
    // Sin dato de soporte se asume que SÍ: el backend clampea igual, y marcar
    // "no soportado" sin saberlo asustaría al operador sin motivo.
    const supported = soporte ? soporte.includes(e.id) : true;
    const effective = supported
      ? e.id
      : (runtimeCatalog?.effort_degrade?.[modelId ?? ""]?.[e.id] ?? e.id);
    return {
      id: e.id,
      label: e.label,
      supported,
      effective,
      note: supported ? "" : `se aplicará como ${effective}`,
    };
  });
}

export function buildModelOptions(
  runtimeCatalog: RuntimeModelCatalog | undefined,
): { id: string; label: string; recommended: boolean }[] {
  const models = runtimeCatalog?.models ?? [];
  const recomendado = runtimeCatalog?.default_model ?? null;
  const anotados = models.map((m) => ({
    id: m.id,
    label: m.label ?? m.id,
    recommended: m.id === recomendado,
  }));
  // El recomendado primero, sin reordenar el resto: es el que el operador elige
  // el 90% de las veces y no tiene por qué buscarlo en el medio de la lista.
  return [...anotados.filter((m) => m.recommended), ...anotados.filter((m) => !m.recommended)];
}

/** Qué ofrece cada runtime. Sale del catálogo, NO de un if por nombre de
 *  runtime: agregar un runtime nuevo no debería obligar a tocar este archivo. */
export function pickerCapabilities(
  runtimeCatalog: RuntimeModelCatalog | undefined,
): { showModels: boolean; showEfforts: boolean; note: string; effortMode: string; effortEffectiveNow: boolean } {
  const showModels = (runtimeCatalog?.models?.length ?? 0) > 0;
  // Plan 264 — un runtime que no expone esfuerzo NO debe mostrar el selector:
  // "prohibido mostrar un selector que no hace nada" (§3.1 del plan).
  const effortMode = runtimeCatalog?.effort_mode ?? "nativo";
  // [C8] Un runtime que SÍ expone esfuerzo pero hoy no produce efecto (Codex
  // sin cap de turnos) muestra el selector CON la nota que lo explica: la
  // elección se guarda y valdrá cuando haya cap. Ocultarlo sería peor: se
  // perdería la elección.
  const effortEffectiveNow = runtimeCatalog?.effort_effective_now ?? true;
  const showEfforts =
    (runtimeCatalog?.efforts?.length ?? 0) > 0 && effortMode !== "no_aplica";
  return {
    showModels,
    showEfforts,
    note: runtimeCatalog?.effort_note ?? runtimeCatalog?.note ?? "",
    effortMode,
    effortEffectiveNow,
  };
}
