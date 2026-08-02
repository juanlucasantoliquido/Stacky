/**
 * publishWizardModel.ts — Plan 293 F13. LÓGICA PURA del tablero de trabajo.
 *
 * Va en `.ts` y no en el `.tsx` porque RTL/jsdom NO están instalados en este
 * repo: un `.test.tsx` con RTL reporta "no tests" y sale con exit 0 — un falso
 * verde perfecto. `vitest` sobre `.ts` sí corre, y esto es lo que se testea; el
 * componente sólo pinta.
 */

export type Paso = "revisar" | "elegir" | "describir" | "confirmar";

/** El orden es el del flujo y NO se deriva de nada: es el contrato de la UI. */
export const PASOS: Paso[] = ["revisar", "elegir", "describir", "confirmar"];

export interface ArchivoCambiado {
  path: string;
  grupo: string;
}

export interface Bloqueo {
  codigo: string;
  severidad?: string;
}

export interface EstadoTablero {
  available: boolean;
  archivos: ArchivoCambiado[];
  conflictos: string[];
  semaforo?: { puede: boolean; bloqueos: Bloqueo[]; avisos: Bloqueo[] };
}

export interface EstadoAsistente {
  paso: Paso;
  seleccion: string[];
  mensaje: string;
  pruebas: string;
}

export const ESTADO_INICIAL: EstadoAsistente = {
  paso: "revisar",
  seleccion: [],
  mensaje: "",
  pruebas: "",
};

/** Rótulos en castellano de cada grupo. Un grupo desconocido NO se pierde. */
export const ROTULO_GRUPO: Record<string, string> = {
  conflictos: "En conflicto",
  modificados: "Modificados",
  nuevos: "Nuevos",
  borrados: "Borrados",
  renombrados: "Renombrados",
  sin_seguimiento: "Sin seguimiento",
  otros: "Otros",
};

/** El orden en que se pintan los grupos. Los conflictos PRIMERO: son lo urgente. */
export const ORDEN_GRUPOS = [
  "conflictos", "modificados", "nuevos", "borrados",
  "renombrados", "sin_seguimiento", "otros",
];

export function rotuloDe(grupo: string): string {
  return ROTULO_GRUPO[grupo] ?? "Otros";
}

/** Agrupa para pintar, en el orden de ORDEN_GRUPOS. Nunca pierde un archivo. */
export function agruparParaPintar(
  archivos: ArchivoCambiado[],
): Array<{ grupo: string; rotulo: string; archivos: ArchivoCambiado[] }> {
  const porGrupo = new Map<string, ArchivoCambiado[]>();
  for (const a of archivos ?? []) {
    const g = ORDEN_GRUPOS.includes(a.grupo) ? a.grupo : "otros";
    if (!porGrupo.has(g)) porGrupo.set(g, []);
    porGrupo.get(g)!.push(a);
  }
  return ORDEN_GRUPOS
    .filter((g) => (porGrupo.get(g)?.length ?? 0) > 0)
    .map((g) => ({ grupo: g, rotulo: rotuloDe(g), archivos: porGrupo.get(g)! }));
}

/**
 * ¿Se puede avanzar del paso actual?
 *
 * Devuelve el CÓDIGO del motivo, no un texto: el castellano lo pone
 * `workbenchErrors.traducir`. Un `null` significa "se puede".
 *
 * Con conflictos presentes NO se avanza NUNCA, desde ningún paso: publicar
 * encima de un conflicto sin resolver es la forma más rápida de romper algo.
 */
export function motivoParaNoAvanzar(
  estado: EstadoAsistente,
  tablero: EstadoTablero,
): string | null {
  if (!tablero.available) return "repo_no_disponible";
  if ((tablero.conflictos ?? []).length > 0) return "conflictos_presentes";

  switch (estado.paso) {
    case "revisar":
      return (tablero.archivos ?? []).length === 0 ? "sin_cambios" : null;
    case "elegir":
      return estado.seleccion.length === 0 ? "nada_seleccionado" : null;
    case "describir":
      return estado.mensaje.trim().length < 5 ? "mensaje_muy_corto" : null;
    case "confirmar":
      return null;
  }
}

export function puedeAvanzar(estado: EstadoAsistente, tablero: EstadoTablero): boolean {
  return motivoParaNoAvanzar(estado, tablero) === null;
}

export function pasoSiguiente(paso: Paso): Paso {
  const i = PASOS.indexOf(paso);
  return i < 0 || i === PASOS.length - 1 ? paso : PASOS[i + 1];
}

export function pasoAnterior(paso: Paso): Paso {
  const i = PASOS.indexOf(paso);
  return i <= 0 ? PASOS[0] : PASOS[i - 1];
}

/** Alterna un archivo en la selección. Inmutable. */
export function alternar(seleccion: string[], path: string): string[] {
  return seleccion.includes(path)
    ? seleccion.filter((p) => p !== path)
    : [...seleccion, path];
}

export interface Resumen {
  elegidos: number;
  total: number;
  noElegidos: number;
  /** Los que quedan AFUERA, por nombre. Se muestran para que el usuario VEA
   *  que existen y que no se tocan — es la regla del riesgo #1. */
  pathsNoElegidos: string[];
}

export function resumenSeleccion(
  seleccion: string[],
  archivos: ArchivoCambiado[],
): Resumen {
  const todos = (archivos ?? []).map((a) => a.path);
  const elegidos = seleccion.filter((p) => todos.includes(p));
  const fuera = todos.filter((p) => !seleccion.includes(p));
  return {
    elegidos: elegidos.length,
    total: todos.length,
    noElegidos: fuera.length,
    pathsNoElegidos: fuera,
  };
}

/** Texto del contador, en castellano y sin jerga. */
export function textoContador(r: Resumen): string {
  if (r.total === 0) return "No hay archivos con cambios.";
  if (r.elegidos === 0) return `Ninguno de los ${r.total} archivos está elegido.`;
  if (r.elegidos === r.total) return `Los ${r.total} archivos están elegidos.`;
  return `${r.elegidos} de ${r.total} archivos elegidos.`;
}

/**
 * Los bloqueos que hay que mostrar EN EL PASO 1, no en el último.
 *
 * Es la regla que `PipelineCopilotSection` ya documentó: avisar al final hace
 * que el usuario recorra todo el asistente para chocarse contra la pared.
 */
export function bloqueosParaElPrimerPaso(tablero: EstadoTablero): string[] {
  const codigos = (tablero.semaforo?.bloqueos ?? []).map((b) => b.codigo);
  // `nada_seleccionado` NO va acá: en el paso 1 todavía no elegiste nada, y
  // mostrarlo como un problema sería mentirle al usuario.
  return codigos.filter((c) => c !== "nada_seleccionado");
}

export function avisosParaElPrimerPaso(tablero: EstadoTablero): string[] {
  return (tablero.semaforo?.avisos ?? []).map((a) => a.codigo);
}
