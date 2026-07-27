/**
 * ledgerHealthModel.ts — Plan 258 F3: núcleo PURO de la tarjeta
 * "Salud de ledgers".
 *
 * Módulo sin JSX y sin red a propósito: `@testing-library/react` y `jsdom` NO
 * están instalados en este frontend (solo vitest), así que un test de render no
 * puede correr. Lo testeable es esto.
 *
 * Qué muestra y por qué importa: los archivos de registro deberían darle al
 * operador visibilidad de lo que la interfaz no enseña. Medido antes de este
 * plan, `ci_runs.jsonl` tenía 8 de 8 líneas de fixture de test y
 * `env_applies.jsonl` 10 de 10 escritas por pytest. Un panel que contara éxitos
 * habría reportado 10 aplicaciones exitosas que nunca ocurrieron.
 *
 * `unknown` NO es `prod` y NO se oculta: una línea histórica sin marca no se
 * puede afirmar como real, y afirmarlo sería inventar el dato.
 */

export type LedgerEnv = "prod" | "test" | "unknown";

export interface LedgerHealthRow {
  name: string;
  total: number;
  prod: number;
  test: number;
  unknown: number;
  /** El archivo tiene lock propio: se puede limpiar de forma segura. */
  purgeable: boolean;
  /** Líneas que la limpieza borraría. Solo `test`; nunca `prod` ni `unknown`. */
  deletable: number;
  /** Confirmación de un solo uso. Solo viene si la limpieza está habilitada. */
  confirm_token: string | null;
}

export interface LedgerOrphan {
  project: string | null;
  tracker_type: string | null;
  pipeline_id: string | null;
  ref: string | null;
  web_url: string | null;
  triggered_at: string | null;
  age_hours: number;
}

export interface LedgerHealthPayload {
  ok?: boolean;
  ledgers?: LedgerHealthRow[] | null;
  orphans?: LedgerOrphan[] | null;
  orphans_enabled?: boolean;
  deletable_total?: number;
  purge_enabled?: boolean;
  confirm_ttl_s?: number;
}

/** Filas a pintar: los archivos con al menos una línea. Un archivo vacío no
 *  aporta nada y solo haría ruido visual. */
export function buildLedgerRows(
  payload: LedgerHealthPayload | null | undefined
): LedgerHealthRow[] {
  if (!payload || payload.ok === false) return [];
  const filas = payload.ledgers;
  if (!Array.isArray(filas)) return [];
  return filas
    .filter((f) => f && typeof f.name === "string" && (f.total ?? 0) > 0)
    .sort((a, b) => (b.test ?? 0) - (a.test ?? 0) || (b.total ?? 0) - (a.total ?? 0));
}

/**
 * ¿Hay algo que reportar? La tarjeta NO se renderiza si todo está limpio: sin
 * líneas de prueba y sin corridas reales sin cerrar no hay nada que decidir.
 *
 * OJO: tener líneas `unknown` NO cuenta como problema. Son el estado honesto de
 * lo histórico y se extinguen solas a medida que entran eventos nuevos ya
 * marcados; alarmar por ellas sería alarmar para siempre.
 */
export function hayAlgoQueReportar(
  payload: LedgerHealthPayload | null | undefined
): boolean {
  if (!payload || payload.ok === false) return false;
  const conTest = buildLedgerRows(payload).some((f) => (f.test ?? 0) > 0);
  const huerfanos = Array.isArray(payload.orphans) ? payload.orphans.length : 0;
  return conTest || huerfanos > 0;
}

/** Etiqueta legible del archivo, sin la extensión técnica. */
export function ledgerLabel(name: string): string {
  const nombres: Record<string, string> = {
    ci_runs: "Corridas de integración continua",
    env_applies: "Aplicaciones de entorno",
    db_query_audit: "Consultas a la base",
    config_transfer_events: "Transferencias de configuración",
    build_runs: "Compilaciones",
  };
  return nombres[name] ?? name;
}

/**
 * Frase exacta que se le muestra al operador ANTES de borrar. Dice qué se
 * elimina, qué NO se toca y que hay copia. Es el contrato humano de la acción
 * destructiva, no un adorno.
 */
export function textoDeLimpieza(fila: LedgerHealthRow): string {
  return (
    `Se eliminarán ${fila.deletable} línea${fila.deletable === 1 ? "" : "s"} de prueba de ` +
    `${fila.name}.jsonl. Las ${fila.prod} de producción y las ${fila.unknown} de ` +
    `procedencia desconocida NO se tocan. Se guarda una copia antes.`
  );
}

/** Resumen de una línea para el encabezado. */
export function resumenDeSalud(payload: LedgerHealthPayload | null | undefined): string {
  const filas = buildLedgerRows(payload);
  const test = filas.reduce((n, f) => n + (f.test ?? 0), 0);
  const total = filas.reduce((n, f) => n + (f.total ?? 0), 0);
  const huerfanos = Array.isArray(payload?.orphans) ? payload!.orphans!.length : 0;
  const partes: string[] = [];
  if (test > 0) partes.push(`${test} de ${total} líneas las escribió una prueba`);
  if (huerfanos > 0) {
    partes.push(
      `${huerfanos} corrida${huerfanos === 1 ? "" : "s"} real${huerfanos === 1 ? "" : "es"} sin cerrar`
    );
  }
  return partes.join(" · ");
}
