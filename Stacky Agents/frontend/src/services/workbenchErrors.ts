/**
 * workbenchErrors.ts — Plan 293 F12.
 *
 * Traduce los CODIGOS que devuelve el backend a castellano llano, para alguien
 * que no sabe git y no tiene por qué saberlo.
 *
 * Va en `.ts` puro y no en un `.tsx`: RTL/jsdom no están instalados en este repo
 * y un `.test.tsx` con RTL reporta "no tests" y sale con exit 0 — un falso verde
 * perfecto. `vitest` sobre `.ts` sí corre.
 *
 * REGLA DURA: ninguna traducción puede contener jerga técnica. Hay un caso que
 * lo vigila palabra por palabra, y se corrió contra su defecto.
 */

export interface Traduccion {
  /** Qué pasó, en una frase corta. */
  titulo: string;
  /** Por qué pasó, sin culpar al usuario. */
  queSignifica: string;
  /** Qué puede hacer AHORA. Siempre accionable, nunca "contacte al administrador". */
  queHacer: string;
  /** `bloqueo` impide seguir; `aviso` sólo informa. */
  tono: "bloqueo" | "aviso";
}

const DICCIONARIO: Record<string, Traduccion> = {
  // ── Estado de la carpeta ────────────────────────────────────────────────
  repo_no_disponible: {
    titulo: "No se puede leer esta carpeta",
    queSignifica: "La carpeta no está preparada para guardar un historial de cambios, o no se pudo consultar.",
    queHacer: "Revisá en Configuración que la carpeta del proyecto sea la correcta.",
    tono: "bloqueo",
  },
  no_es_repositorio: {
    titulo: "Esta carpeta no lleva historial",
    queSignifica: "La carpeta existe, pero no está preparada para ir guardando versiones de tu trabajo.",
    queHacer: "Elegí una carpeta que ya esté preparada, o pedile a alguien del equipo que la prepare.",
    tono: "bloqueo",
  },
  otra_operacion_en_curso: {
    titulo: "La carpeta está ocupada",
    queSignifica: "Otro programa o ventana está trabajando sobre esta misma carpeta en este momento.",
    queHacer: "Esperá unos segundos y volvé a intentar.",
    tono: "bloqueo",
  },
  operacion_en_curso: {
    titulo: "Quedó algo a medio terminar",
    queSignifica: "En esta carpeta empezó una operación que nunca se completó, y hasta que se cierre no se puede guardar sólo una parte de los cambios.",
    queHacer: "Pedile ayuda a alguien del equipo para cerrar esa operación pendiente. Tu trabajo no se pierde.",
    tono: "bloqueo",
  },
  tiempo_agotado: {
    titulo: "La operación tardó demasiado",
    queSignifica: "No hubo respuesta a tiempo. Suele pasar con carpetas muy grandes o con la conexión lenta.",
    queHacer: "Volvé a intentar. Si sigue igual, avisá al equipo.",
    tono: "bloqueo",
  },

  // ── Elegir archivos ─────────────────────────────────────────────────────
  sin_cambios: {
    titulo: "No hay nada para guardar",
    queSignifica: "Los archivos de esta carpeta están igual que la última vez que se guardaron.",
    queHacer: "Hacé algún cambio y volvé acá.",
    tono: "bloqueo",
  },
  nada_seleccionado: {
    titulo: "No elegiste ningún archivo",
    queSignifica: "Hay que tildar al menos un archivo para poder guardarlo.",
    queHacer: "Tildá los archivos que quieras incluir en la lista de arriba.",
    tono: "bloqueo",
  },
  ruta_invalida: {
    titulo: "Uno de los archivos elegidos no es válido",
    queSignifica: "Alguno de los archivos que se enviaron no está dentro de la carpeta del proyecto.",
    queHacer: "Recargá la pantalla y volvé a elegir los archivos.",
    tono: "bloqueo",
  },
  ruta_es_carpeta: {
    titulo: "Elegiste una carpeta entera",
    queSignifica: "Una carpeta arrastraría también cambios de otras personas que están trabajando acá.",
    queHacer: "Elegí los archivos uno por uno.",
    tono: "bloqueo",
  },
  conflictos_presentes: {
    titulo: "Hay archivos con dos versiones enfrentadas",
    queSignifica: "Vos y otra persona cambiaron las mismas líneas de un archivo, y hay que decidir cuál queda.",
    queHacer: "Abrí los archivos marcados en rojo y dejá una sola versión. Después volvé acá.",
    tono: "bloqueo",
  },

  // ── Guardar ─────────────────────────────────────────────────────────────
  no_se_pudo_guardar: {
    titulo: "No se pudo guardar",
    queSignifica: "La operación falló antes de terminar. Tus archivos quedaron como estaban.",
    queHacer: "Volvé a intentar. Si sigue fallando, avisá al equipo con una captura de esta pantalla.",
    tono: "bloqueo",
  },

  // ── Enviar ──────────────────────────────────────────────────────────────
  envio_rechazado: {
    titulo: "Alguien subió cambios antes que vos",
    queSignifica: "El servidor tiene trabajo más nuevo que el tuyo, y por eso no aceptó lo que enviaste. No se perdió nada.",
    queHacer: 'Tocá "Traer cambios" para incorporar lo de tus compañeros y después volvé a enviar.',
    tono: "bloqueo",
  },
  sin_permiso_en_el_servidor: {
    titulo: "El servidor no aceptó tus credenciales",
    queSignifica: "Tu clave de acceso al servidor está vencida o no alcanza para esta carpeta.",
    queHacer: "Revisá en Configuración la clave de acceso del proyecto.",
    tono: "bloqueo",
  },
  no_se_pudo_enviar: {
    titulo: "No se pudo enviar",
    queSignifica: "No hubo respuesta del servidor. Tu trabajo sigue guardado en tu máquina.",
    queHacer: "Revisá tu conexión y volvé a intentar.",
    tono: "bloqueo",
  },
  sin_upstream: {
    titulo: "Esta versión de trabajo todavía no está en el servidor",
    queSignifica: "Nunca se envió, así que no hay con qué compararla ni de dónde traer novedades.",
    queHacer: "Enviá tu trabajo una primera vez y después vas a poder traer cambios.",
    tono: "bloqueo",
  },
  rama_invalida: {
    titulo: "El nombre de la versión de trabajo no sirve para enviar",
    queSignifica: "Ese nombre tiene símbolos que cambiarían el significado del envío.",
    queHacer: "Elegí un nombre con letras, números, puntos, guiones y barras.",
    tono: "bloqueo",
  },

  // ── Versiones de trabajo ────────────────────────────────────────────────
  nombre_invalido: {
    titulo: "Ese nombre no sirve",
    queSignifica: "El nombre tiene espacios o símbolos que no se pueden usar.",
    queHacer: "Usá letras, números, puntos, guiones y barras. Por ejemplo: mejoras/pantalla-de-clientes",
    tono: "bloqueo",
  },
  cambio_bloqueado_por_trabajo_sin_guardar: {
    titulo: "Tenés cambios sin guardar",
    queSignifica: "Si cambiás de versión de trabajo ahora, esos cambios se perderían. Por eso no se hizo nada.",
    queHacer: "Guardá tus cambios primero y después cambiá de versión.",
    tono: "bloqueo",
  },
  la_version_ya_existe: {
    titulo: "Ya existe una versión con ese nombre",
    queSignifica: "No se puede tener dos versiones de trabajo con el mismo nombre.",
    queHacer: "Elegí otro nombre, o cambiate a la que ya existe.",
    tono: "bloqueo",
  },
  version_inexistente: {
    titulo: "No existe esa versión de trabajo",
    queSignifica: "El nombre que pediste no está en esta carpeta.",
    queHacer: "Elegí una de la lista.",
    tono: "bloqueo",
  },
  no_se_pudo_cambiar: {
    titulo: "No se pudo cambiar de versión de trabajo",
    queSignifica: "La operación falló antes de terminar. Seguís donde estabas.",
    queHacer: "Volvé a intentar. Si sigue fallando, avisá al equipo.",
    tono: "bloqueo",
  },

  // ── Opciones apagadas (403 acá significa "apagado", no "sin permiso") ───
  escritura_apagada: {
    titulo: "Guardar cambios está desactivado",
    queSignifica: "La opción que permite que el tablero modifique tu carpeta viene apagada de fábrica.",
    queHacer: 'Encendé "Dejar que el tablero guarde cambios en tu carpeta" en el panel de opciones.',
    tono: "bloqueo",
  },
  push_apagado: {
    titulo: "Enviar al servidor está desactivado",
    queSignifica: "La opción que permite que el tablero suba tu trabajo viene apagada de fábrica.",
    queHacer: 'Encendé "Dejar que el tablero envíe tu trabajo al servidor" en el panel de opciones.',
    tono: "bloqueo",
  },

  // ── Avisos: informan, NO bloquean ───────────────────────────────────────
  hay_cambios_no_seleccionados: {
    titulo: "Hay archivos que no elegiste",
    queSignifica: "Se van a guardar sólo los que tildaste. Los demás quedan como están, sin tocarse.",
    queHacer: "Si querés incluirlos, tildalos antes de continuar.",
    tono: "aviso",
  },
  rama_sin_upstream: {
    titulo: "Esta versión de trabajo todavía no está en el servidor",
    queSignifica: "Podés guardar igual: se envía cuando vos quieras.",
    queHacer: "No hace falta hacer nada ahora.",
    tono: "aviso",
  },
  carrera_working_tree: {
    titulo: "Otras personas pueden estar tocando estos archivos",
    queSignifica: "Se guarda lo que haya en el archivo en el momento de guardar, que puede no ser exactamente lo que ves ahora.",
    queHacer: "Si dudás, mirá las diferencias de cada archivo antes de continuar.",
    tono: "aviso",
  },
  identidad_derivada: {
    titulo: "Tu nombre no está configurado",
    queSignifica: "Lo guardado va a quedar firmado con un nombre armado automáticamente a partir de tu usuario y tu máquina.",
    queHacer: "Podés continuar igual. Si querés que figure tu nombre real, pedile al equipo que lo configure.",
    tono: "aviso",
  },
};

/** Jerga que NUNCA puede aparecer en una traducción. La lee el usuario final. */
export const JERGA_PROHIBIDA = [
  "git", "commit", "branch", "head", "upstream", "merge", "porcelain",
  "fast-forward", "index", "push", "pull", "stage", "checkout", "rebase",
  "repositorio", "pathspec", "refspec", "remote",
];

const GENERICO: Traduccion = {
  titulo: "Algo no salió como esperábamos",
  queSignifica: "La operación no se completó. Tus archivos quedaron como estaban.",
  queHacer: "Volvé a intentar. Si vuelve a pasar, sacá una captura de esta pantalla y avisá al equipo.",
  tono: "bloqueo",
};

/** Traduce un código del backend. Un código desconocido NO devuelve el código
 *  crudo: devuelve un texto genérico que igual le dice al usuario qué hacer. */
export function traducir(codigo: string | null | undefined): Traduccion {
  if (!codigo) return GENERICO;
  return DICCIONARIO[codigo] ?? GENERICO;
}

/** Los códigos que este diccionario cubre. Lo usa el gate de cobertura. */
export function codigosCubiertos(): string[] {
  return Object.keys(DICCIONARIO);
}
