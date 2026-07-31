/**
 * lib/jerarquiaLocal.ts — Plan 277 F4. La lógica del control de jerarquía local.
 *
 * POR QUÉ TODO ESTO VIVE EN UN `.ts` PURO: este repo NO tiene RTL ni jsdom, así que
 * nada que esté escrito adentro de un componente es verificable automáticamente. La
 * regla "¿muestro el control?" y la validación del `iid` son justo lo que no puede
 * quedar sin test: la primera decide si el operador ve la función, y la segunda es
 * lo que evita mandar al servidor un padre que tumbaría el grafo.
 *
 * El render se cubre con el smoke manual de 10 pasos del plan.
 */

/** La flag que gatea la fase. Mismo nombre exacto que registra el arnés. */
export const FLAG_JERARQUIA_LOCAL = "STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED";

/**
 * Los 8 tipos canónicos, en el MISMO orden y con los MISMOS valores que
 * `TIPOS_CANONICOS` de `backend/services/gitlab_hierarchy.py`. El `valor` es lo que
 * viaja al servidor; el `rotulo` es lo único que se traduce para la pantalla.
 */
export const TIPOS_CANONICOS_JERARQUIA = [
  { valor: "Epic", rotulo: "Épica" },
  { valor: "Funcional", rotulo: "Funcional" },
  { valor: "Tecnico", rotulo: "Técnico" },
  { valor: "Implementacion", rotulo: "Implementación" },
  { valor: "Bug", rotulo: "Error" },
  { valor: "Task", rotulo: "Tarea" },
  { valor: "Feature", rotulo: "Funcionalidad" },
  { valor: "Issue", rotulo: "Incidencia" },
] as const;

export interface TicketJerarquiaLocal {
  ado_id?: number | null;
  tracker_type?: string | null;
  local_work_item_type?: string | null;
  local_parent_iid?: number | null;
}

/**
 * ¿Se renderiza el control de jerarquía local para este ticket?
 *
 * Las TRES condiciones, y la tercera es la que se olvida: la clave
 * `local_work_item_type` tiene que estar PRESENTE en el payload. Con
 * `STACKY_CANONICAL_VOCABULARY_ENABLED` apagada, `Ticket.to_dict()` devuelve el
 * `_legacy_payload()` de 16 claves exactas —contrato byte-idéntico del plan 218 F5,
 * que este plan tiene PROHIBIDO tocar— y las dos claves nuevas no viajan. Renderizar
 * igual mostraría un control que abre vacío y que, al guardar, pisaría con `null` lo
 * que el operador ya tenía cargado.
 *
 * Se usa `hasOwnProperty` y no `!= null` a propósito: `null` es un valor legítimo
 * ("todavía no clasificado") y no puede confundirse con "el servidor no lo manda".
 */
export function debeMostrarControlJerarquia(
  ticket: TicketJerarquiaLocal | null | undefined,
  flagOn: boolean,
): boolean {
  if (!ticket || !flagOn) return false;
  if ((ticket.tracker_type ?? "").toLowerCase() !== "gitlab") return false;
  return Object.prototype.hasOwnProperty.call(ticket, "local_work_item_type");
}

export type CodigoErrorPadre = "no_entero" | "no_positivo" | "auto_padre";

export type ValidacionPadre =
  | { ok: true; valor: number | null }
  | { ok: false; codigo: CodigoErrorPadre; mensaje: string };

/**
 * Valida el `iid` del padre que escribió el operador.
 *
 * Vacío ⇒ `{ ok: true, valor: null }`: null BORRA la clasificación local, que es
 * exactamente lo que el servidor hace con `null` en ese campo.
 *
 * El auto-padre se corta ACÁ además de en el servidor: `parent === self` hace que
 * `get_hierarchy` arme una auto-referencia y que `jsonify` levante
 * `Circular reference detected` ⇒ 500 y la pantalla del grafo en blanco. Validar de
 * los dos lados no es redundancia: el servidor protege el dato, esto protege al
 * operador de un viaje perdido.
 */
export function validarPadre(
  crudo: string | number | null | undefined,
  ticket: TicketJerarquiaLocal | null | undefined,
): ValidacionPadre {
  const texto = crudo === null || crudo === undefined ? "" : String(crudo).trim();
  if (texto === "") return { ok: true, valor: null };

  if (!/^-?\d+$/.test(texto)) {
    return {
      ok: false,
      codigo: "no_entero",
      mensaje: `"${texto}" no es un número de ticket. Poné solo el número, sin letras ni puntos.`,
    };
  }
  const iid = Number(texto);
  if (iid <= 0) {
    return {
      ok: false,
      codigo: "no_positivo",
      mensaje: "El número del ticket padre tiene que ser mayor que cero.",
    };
  }
  if (ticket?.ado_id != null && iid === ticket.ado_id) {
    return {
      ok: false,
      codigo: "auto_padre",
      mensaje: "Un ticket no puede colgar de sí mismo.",
    };
  }
  return { ok: true, valor: iid };
}

/** Rótulo visible de un tipo. Lo desconocido no se descarta: se muestra tal cual. */
export function rotuloDeTipo(valor: string | null | undefined): string {
  if (!valor) return "";
  const encontrado = TIPOS_CANONICOS_JERARQUIA.find((t) => t.valor === valor);
  return encontrado ? encontrado.rotulo : valor;
}

/** Valor inicial del input de padre: "" cuando no hay clasificación local. */
export function valorInicialPadre(ticket: TicketJerarquiaLocal | null | undefined): string {
  const iid = ticket?.local_parent_iid;
  return iid == null ? "" : String(iid);
}

/* ── Plan 277 F5 — publicar la clasificación local COMO ETIQUETAS en GitLab ──
 *
 * Misma disciplina que arriba: acá vive lo verificable (qué se puede tocar, qué se
 * preselecciona, qué dice el aviso) y en el componente queda solo el render. Lo que
 * esta lógica protege es concreto: el botón de publicar dispara la ÚNICA escritura
 * del plan en el sistema real del operador.
 */

/** La flag que gatea la ESCRITURA. Ver el diff no la necesita: es read-only. */
export const FLAG_PUBLICAR_ETIQUETAS = "STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED";

export interface CambioBackfill {
  ado_id: number;
  iid: number;
  title: string;
  url: string;
  agregar: string[];
  ya_tiene: string[];
  conflicto: boolean;
  error?: string;
}

export interface PlanBackfill {
  proyecto: string;
  total: number;
  cambios: CambioBackfill[];
  con_conflicto: number;
}

/**
 * ¿Este ítem del diff se puede publicar?
 *
 * Las DOS condiciones: que no esté en conflicto (GitLab ya dice otra cosa y manda) y
 * que haya algo que agregar. La segunda es la que hace idempotente a la segunda
 * corrida: un issue que ya tiene la etiqueta no vuelve a viajar.
 *
 * El servidor rechaza igual los dos casos: esto NO es la defensa, es no hacerle
 * perder el viaje al operador ni ofrecerle un botón que no va a hacer nada.
 */
export function esPublicable(cambio: CambioBackfill | null | undefined): boolean {
  if (!cambio || cambio.conflicto) return false;
  return (cambio.agregar?.length ?? 0) > 0;
}

/** Preselección: todo lo publicable. Lo que está en conflicto NUNCA se preselecciona. */
export function seleccionInicialBackfill(plan: PlanBackfill | null | undefined): number[] {
  return (plan?.cambios ?? []).filter(esPublicable).map((c) => c.ado_id);
}

/** Marca/desmarca un ítem. Lo no publicable no entra ni aunque se lo pida. */
export function alternarSeleccion(
  seleccion: number[],
  cambio: CambioBackfill,
): number[] {
  if (seleccion.includes(cambio.ado_id)) return seleccion.filter((x) => x !== cambio.ado_id);
  if (!esPublicable(cambio)) return seleccion;
  return [...seleccion, cambio.ado_id];
}

export interface EstadoBotonPublicar {
  habilitado: boolean;
  rotulo: string;
  /** Por qué está deshabilitado. Vacío cuando se puede apretar. */
  hint: string;
}

/**
 * El estado del botón "Publicar etiquetas en GitLab".
 *
 * Con la flag apagada el botón se deshabilita y el aviso NOMBRA la flag y dónde
 * encenderla: un control gris sin explicación manda al operador a leer código, que es
 * el defecto que ya documentó este repo con los tabs que nacían apagados.
 */
export function estadoBotonPublicar(
  flagOn: boolean,
  seleccion: number[],
  publicando = false,
): EstadoBotonPublicar {
  if (!flagOn) {
    return {
      habilitado: false,
      rotulo: "Publicar etiquetas en GitLab",
      hint:
        `Está apagado. Encendé ${FLAG_PUBLICAR_ETIQUETAS} en el panel de flags del ` +
        `arnés. Ver qué cambiaría no necesita esa flag: eso ya funciona.`,
    };
  }
  if (publicando) {
    return { habilitado: false, rotulo: "Publicando…", hint: "" };
  }
  if (seleccion.length === 0) {
    return {
      habilitado: false,
      rotulo: "Publicar etiquetas en GitLab",
      hint: "Elegí al menos un ticket. Nunca se publica todo por defecto.",
    };
  }
  return {
    habilitado: true,
    rotulo: `Publicar etiquetas en GitLab (${seleccion.length})`,
    hint: "",
  };
}

/** Resumen del diff para el encabezado: qué se toca y qué no. */
export function resumenBackfill(plan: PlanBackfill | null | undefined): {
  total: number;
  publicables: number;
  conflictos: number;
  sinCambios: number;
} {
  const cambios = plan?.cambios ?? [];
  const publicables = cambios.filter(esPublicable).length;
  const conflictos = cambios.filter((c) => c.conflicto).length;
  return {
    total: cambios.length,
    publicables,
    conflictos,
    sinCambios: cambios.length - publicables - conflictos,
  };
}
