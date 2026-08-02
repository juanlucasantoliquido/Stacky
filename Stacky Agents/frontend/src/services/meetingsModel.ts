/**
 * Plan 283 F9 — Modelo de la pantalla de Reuniones. LOGICA PURA, sin React.
 *
 * Por que vive en un `.ts` y no dentro del `.tsx`: RTL y jsdom NO estan
 * instalados en este repo. Un `.test.tsx` con RTL reporta "no tests" y sale con
 * codigo 0 — un falso verde perfecto. Toda la logica testeable vive aca; el
 * `.tsx` queda como cascara de pintura y se verifica con un smoke manual.
 *
 * El formateo de fechas sale de `services/format` a proposito: es el unico
 * modulo autorizado a usar los formateadores nativos (formatDebtRatchet).
 */
import { formatDate } from "./format";

export type MeetingsView = "calendario" | "detalle";

export type MinutesState = "pending" | "done" | "failed" | "blocked";

export interface MeetingRow {
  id: number;
  subject: string;
  startedAt: string | null;
  minutesState: MinutesState;
  pendientes: number;
}

export const GRUPO_SIN_FECHA = "Sin fecha";

export interface GrupoDeDia {
  dia: string;
  rows: MeetingRow[];
}

/**
 * Agrupa por dia LOCAL y ordena de mas reciente a mas viejo. El grupo de las
 * reuniones sin fecha va SIEMPRE al final: no se descartan ni se esconden.
 */
export function agruparPorDia(rows: MeetingRow[]): GrupoDeDia[] {
  const grupos = new Map<string, { dia: string; orden: number; rows: MeetingRow[] }>();
  for (const row of rows ?? []) {
    const ts = row.startedAt ? Date.parse(row.startedAt) : Number.NaN;
    const conFecha = !Number.isNaN(ts);
    const dia = conFecha ? formatDate(row.startedAt, "local") : GRUPO_SIN_FECHA;
    const actual = grupos.get(dia);
    if (actual) {
      actual.rows.push(row);
      if (conFecha) actual.orden = Math.max(actual.orden, ts);
    } else {
      grupos.set(dia, {
        dia,
        // Sin fecha: -Infinity para que quede ultimo en orden descendente.
        orden: conFecha ? ts : Number.NEGATIVE_INFINITY,
        rows: [row],
      });
    }
  }
  return [...grupos.values()]
    .sort((a, b) => b.orden - a.orden)
    .map((g) => ({
      dia: g.dia,
      rows: [...g.rows].sort((a, b) => {
        const ta = a.startedAt ? Date.parse(a.startedAt) : Number.NEGATIVE_INFINITY;
        const tb = b.startedAt ? Date.parse(b.startedAt) : Number.NEGATIVE_INFINITY;
        return tb - ta;
      }),
    }));
}

/** Estado de la minuta, en castellano y sin jerga. */
export function etiquetaEstadoMinuta(s: MeetingRow["minutesState"]): string {
  switch (s) {
    case "done":
      return "Minuta lista";
    case "failed":
      return "No se pudo generar";
    case "blocked":
      return "Frenada por datos sensibles";
    case "pending":
    default:
      return "Sin texto todavia";
  }
}

/**
 * Un compromiso se puede publicar solo si la capacidad esta encendida Y todavia
 * no se publico. Nunca se ofrece publicar dos veces el mismo.
 */
export function puedePublicar(item: { estado: string }, flagOn: boolean): boolean {
  if (!flagOn) return false;
  return (item?.estado ?? "") === "propuesto";
}

/** Traduce el estado del calendario a algo que el operador pueda accionar. */
export function resumenCalendario(estado: string): { texto: string; accionable: boolean } {
  switch (estado) {
    case "ok":
      return { texto: "Calendario al dia.", accionable: false };
    case "apagado":
      return {
        texto: "La conexion con el calendario esta apagada. Podes cargar la reunion a mano.",
        accionable: false,
      };
    case "sin_credenciales":
      return {
        texto:
          "Falta el identificador de la aplicacion de Microsoft y hacer el ingreso una vez. " +
          "Cargalo en Configuracion y volve.",
        accionable: true,
      };
    case "error":
      return {
        texto: "No se pudo leer el calendario. Proba de nuevo o volve a hacer el ingreso.",
        accionable: true,
      };
    default:
      return { texto: "Estado desconocido del calendario.", accionable: true };
  }
}

export interface AccionReunion {
  id: "importar" | "regenerar" | "publicar" | "actualizar";
  label: string;
  habilitada: boolean;
  /**
   * SIEMPRE null. El objetivo de esta pantalla es que el ciclo entero — de la
   * transcripcion al borrador de tarea — pase en UN solo lugar. Una accion con
   * ruta a otra seccion violaria eso, asi que el tipo no la admite.
   */
  navPath: null;
}

/**
 * Las CUATRO acciones del ciclo, SIEMPRE las cuatro. Lo que cambia es
 * `habilitada`, nunca la presencia: una accion que desaparece deja al operador
 * sin saber que existe. Se muestra deshabilitada con su motivo.
 */
export function accionesDisponibles(
  m: MeetingRow,
  flags: { publishOn: boolean },
): AccionReunion[] {
  const tieneMinuta = m?.minutesState === "done";
  const seIntento = m?.minutesState !== "pending";
  return [
    { id: "importar", label: "Cargar lo que se dijo", habilitada: true, navPath: null },
    { id: "regenerar", label: "Volver a generar la minuta", habilitada: seIntento, navPath: null },
    {
      id: "publicar",
      label: "Crear tarea desde un compromiso",
      habilitada: Boolean(flags?.publishOn) && tieneMinuta && (m?.pendientes ?? 0) > 0,
      navPath: null,
    },
    { id: "actualizar", label: "Actualizar el calendario", habilitada: true, navPath: null },
  ];
}
