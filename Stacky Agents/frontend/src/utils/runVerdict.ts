// Plan 269 F3 — veredicto por evidencia → etiqueta + tono + explicación.
//
// Reusa OutcomeTone de outcomeReason.ts (254 F4): NO se define un tipo de tono
// nuevo. El veredicto es una DIMENSIÓN SEPARADA del estado, no un estado más.

import type { OutcomeTone } from "./outcomeReason";

export type VerdictLevel = "exito" | "advertencia" | "error_real";

export interface RunVerdictPayload {
  level: string;
  cause: string;
  strength?: number;
  present?: string[];
  absent?: string[];
  unknown?: string[];
}

export interface VerdictView {
  level: VerdictLevel;
  tone: OutcomeTone;      // "exito" | "atencion" | "espera" | "error"
  label: string;          // texto del chip de la fila, corto
  detail: string;         // una línea explicando la causa
  needsOperator: boolean; // true ⇒ merece un ojo humano
}

/** Los 3 niveles → tono + etiqueta corta de fila. */
export const VERDICT_LEVEL_VIEW: Record<VerdictLevel, { tone: OutcomeTone; label: string }> = {
  exito:       { tone: "exito",    label: "Terminó bien" },
  advertencia: { tone: "atencion", label: "Con advertencias" },
  error_real:  { tone: "error",    label: "Error real" },
};

/** Las 9 causas de VERDICT_CAUSES (services/run_verdict.py), ni una más ni una
 *  menos. El drift contra el .py lo ATRAPA `test_20_espejo_ts_no_tiene_drift`
 *  del backend: esto ya no es un comentario de buena fe. */
export const VERDICT_CAUSE_DETAIL: Record<string, string> = {
  cierre_limpio_con_entrega: "Terminó sin errores y dejó resultados verificables.",
  verde_sin_evidencia: "Figura como terminado, pero no se encontró ningún resultado que lo respalde.",
  evidencia_indeterminada: "Figura como terminado, pero no se pudo comprobar si dejó resultados.",
  cierre_sucio_pendiente_de_revision: "Entregó trabajo pero el proceso cerró mal: convendría mirarlo.",
  cancelado_por_el_operador: "Lo cortaste vos. No es una falla del sistema.",
  falso_rojo_probable: "Figura como fallado, pero hay resultados: probablemente NO sea un error.",
  espera_cuota: "Se agotó la cuota del plan. No es un error del trabajo: hay que reintentar más tarde.",
  error_sin_entrega_suficiente: "Falló y no se encontraron resultados: requiere atención.",
  bloqueado_antes_de_empezar: "Se bloqueó antes de arrancar: nunca llegó a trabajar.",
};

/** Nombres humanos de EVIDENCE_SIGNALS (services/run_verdict.py). */
export const EVIDENCE_LABELS: Record<string, string> = {
  publicado_en_tracker: "comentario publicado en el tablero",
  cambio_en_repo: "cambios en el repositorio",
  gate_aceptacion_ok: "criterios de aceptación verificados",
  verificacion_ok: "verificación de la ejecución",
  entregable_presente: "archivo de resultado",
};

const NIVELES: VerdictLevel[] = ["exito", "advertencia", "error_real"];

/** Causas que tienen un tono PROPIO, más específico que el del nivel.
 *  `espera_cuota` NO es lo mismo que "con advertencias": el trabajo no falló,
 *  se agotó la cuota y hay que reintentar más tarde. `OutcomeTone` ya tiene el
 *  vocabulario ("espera"); resolver el tono SOLO por nivel dejaba
 *  `verdictChipTone("espera")` como rama muerta.
 *  El NIVEL no cambia (sigue siendo `advertencia`): solo cambia cómo se pinta. */
export const VERDICT_CAUSE_TONE: Record<string, OutcomeTone> = {
  espera_cuota: "espera",
};

/**
 * Traduce el veredicto. Un nivel o causa del futuro NO rompe la UI: cae a
 * "advertencia" con el texto crudo, nunca a `undefined` y NUNCA a "exito"
 * (un nivel desconocido jamás se presenta como éxito).
 */
export function describeVerdict(v: RunVerdictPayload | null | undefined): VerdictView | null {
  if (!v || !v.level) return null;
  const level: VerdictLevel = (NIVELES as string[]).includes(v.level)
    ? (v.level as VerdictLevel)
    : "advertencia";
  const view = VERDICT_LEVEL_VIEW[level];
  return {
    level,
    tone: VERDICT_CAUSE_TONE[v.cause] ?? view.tone,   // la causa gana
    label: view.label,
    detail: VERDICT_CAUSE_DETAIL[v.cause] ?? v.cause,
    needsOperator: level !== "exito",
  };
}

/** Frase de evidencia para el detalle: qué se encontró y qué no. */
export function evidenceSummary(v: RunVerdictPayload | null | undefined): string {
  if (!v) return "";
  const nombre = (k: string) => EVIDENCE_LABELS[k] ?? k;
  const partes: string[] = [];
  if (v.present?.length) partes.push(`Se encontró: ${v.present.map(nombre).join(", ")}.`);
  if (v.absent?.length) partes.push(`No hay: ${v.absent.map(nombre).join(", ")}.`);
  if (v.unknown?.length) partes.push(`No se pudo comprobar: ${v.unknown.map(nombre).join(", ")}.`);
  return partes.join(" ");
}

/** Filtro por nivel para las listas. `null`/"" = sin filtro (devuelve todo). */
export function matchesVerdictLevel(
  v: RunVerdictPayload | null | undefined,
  filtro: string | null | undefined,
): boolean {
  if (!filtro) return true;
  const view = describeVerdict(v);
  if (!view) return false;   // sin veredicto no matchea un filtro explícito
  return view.level === filtro;
}

/** Puente de tonos. `StatusChip` usa StatusTone ("success"|"warning"|"danger"|
 *  "info"|"neutral", utils/runStatus.ts:1). OutcomeTone es otro vocabulario.
 *  Vive acá y no en el .tsx para no acoplar `utils/` a `ui/`. */
export function verdictChipTone(tone: OutcomeTone): "success" | "warning" | "danger" | "neutral" {
  if (tone === "exito") return "success";
  if (tone === "error") return "danger";
  if (tone === "espera") return "neutral";
  return "warning";
}
