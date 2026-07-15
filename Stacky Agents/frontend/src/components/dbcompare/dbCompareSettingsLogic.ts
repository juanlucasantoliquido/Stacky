// Plan 122-126 — lógica pura de la sección "Configuración" del Comparador de BD.
// Sin dependencias de React: testeable con vitest puro (gap RTL/jsdom preexistente,
// ver envForm.ts:1-3). Reusa el registry de flags del arnés (services/harness_flags.py,
// categorías "capacidades_optin" + "comparador_bd") como fuente ÚNICA — no duplica
// almacenamiento: esta sección es un subconjunto filtrado + editable del mismo
// GET/PUT /api/harness-flags que ya usa HarnessFlagsPanel.
import type { HarnessFlagView } from "../../api/endpoints";

// Las 4 flags de la serie 122-126 que el operador puede necesitar ajustar sin
// salir del tab: master + los 3 knobs de la categoría "comparador_bd".
export const DB_COMPARE_SETTINGS_KEYS = [
  "STACKY_DB_COMPARE_ENABLED",
  "STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC",
  "STACKY_DB_COMPARE_DATA_DIFF_ENABLED",
  "STACKY_DB_COMPARE_DATA_MAX_ROWS",
] as const;

export type DbCompareSettingKey = (typeof DB_COMPARE_SETTINGS_KEYS)[number];

/**
 * Filtra + ordena (mismo orden que DB_COMPARE_SETTINGS_KEYS) las flags del
 * arnés que pertenecen a la Configuración de DB Compare. Flags ausentes del
 * registry (backend viejo/drift) se omiten en vez de romper el render.
 */
export function pickDbCompareSettings(flags: HarnessFlagView[]): HarnessFlagView[] {
  const byKey = new Map(flags.map((f) => [f.key, f]));
  return DB_COMPARE_SETTINGS_KEYS.map((k) => byKey.get(k)).filter(
    (f): f is HarnessFlagView => f != null,
  );
}

export interface IntValidation {
  ok: boolean;
  error?: string;
  value?: number;
}

/** Valida un input numérico contra los bounds declarados por la flag (Plan 83). */
export function validateIntSetting(
  raw: string,
  minValue: number | null,
  maxValue: number | null,
): IntValidation {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { ok: false, error: "Requerido." };
  }
  const n = Number(trimmed);
  if (!Number.isInteger(n)) {
    return { ok: false, error: "Debe ser un entero." };
  }
  if (minValue != null && n < minValue) {
    return { ok: false, error: `Mínimo permitido: ${minValue}.` };
  }
  if (maxValue != null && n > maxValue) {
    return { ok: false, error: `Máximo permitido: ${maxValue}.` };
  }
  return { ok: true, value: n };
}
