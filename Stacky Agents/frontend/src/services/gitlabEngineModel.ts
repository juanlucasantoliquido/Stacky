/**
 * gitlabEngineModel.ts — Plan 290 F5.
 *
 * Lógica PURA del master switch de GitLab. El GET de `/api/global-config`
 * devuelve el valor tal como está en el archivo de configuración, o sea un
 * STRING, no un booleano — normalizarlo mal es la diferencia entre "el motor está
 * encendido" y "el motor dice que está encendido".
 *
 * La tabla de valores verdaderos es EXACTAMENTE la del backend
 * (`config.py:1297-1299` y el hot-apply de `api/global_config.py`): `1`, `true`,
 * `yes`. `on` NO está a propósito: agregarlo divergiría del arranque, y entonces
 * la interfaz mostraría encendido algo que al reiniciar nace apagado.
 */

/** Los tres únicos valores que el backend considera verdaderos. */
const VERDADEROS = new Set(["1", "true", "yes"]);

/** Normaliza el string del archivo de configuración a booleano. Nunca lanza. */
export function estaEncendido(valor: unknown): boolean {
  if (typeof valor === "boolean") return valor;
  if (typeof valor !== "string") return false;
  return VERDADEROS.has(valor.trim().toLowerCase());
}

/**
 * Lo que se manda en el PUT. SIEMPRE los strings `"true"`/`"false"`, nunca un
 * booleano ni `null`: `api/global_config.py:203` hace `str(data[key] or "").strip()`,
 * así que un `false` booleano o un `null` llegan como `""` y dejan el archivo con
 * la línea `STACKY_GITLAB_ENABLED=` — consistente, pero ilegible para el operador.
 */
export function valorParaGuardar(encendido: boolean): "true" | "false" {
  return encendido ? "true" : "false";
}

/** Aviso al apagar: los proyectos GitLab empiezan a fallar. No es un toggle mudo. */
export function avisoDeApagado(encendido: boolean): string | null {
  if (encendido) return null;
  return (
    "Con el motor de GitLab apagado, los proyectos que usan GitLab dejan de " +
    "resolver su tracker y sus operaciones fallan con un error de configuración."
  );
}
