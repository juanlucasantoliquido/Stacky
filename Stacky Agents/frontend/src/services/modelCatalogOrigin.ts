import type { ModelCatalogResponse } from "../api/endpoints";

/** Plan 288 F9 — qué contarle al operador sobre el ORIGEN de la lista de modelos.
 *
 * Toda la lógica verificable vive acá, en `.ts` puro: en este repositorio no
 * están instalados @testing-library/react ni jsdom, así que un componente no se
 * puede montar en una prueba. El `.tsx` queda tonto y esto se prueba entero.
 */

export type NivelAviso = "ok" | "respaldo" | "parcial";

export interface AvisoCatalogo {
  nivel: NivelAviso;
  /** Texto listo para mostrar. Vacío cuando nivel === "ok". */
  texto: string;
  /** Detalle opcional para el `title` del elemento. Vacío si no hay. */
  detalle: string;
}

const OK: AvisoCatalogo = { nivel: "ok", texto: "", detalle: "" };

/** Motivo técnico del filtro de admisión -> castellano para el operador. */
const MOTIVO_EN_CASTELLANO: Record<string, string> = {
  otro_proveedor: "no es un modelo de Claude Code",
  bloqueado_por_politica_de_costo: "Stacky lo tiene bloqueado por política de costo",
};

/** Motivo por el que no se pudo leer la cuenta -> castellano. */
const MOTIVO_CUENTA: Record<string, string> = {
  flag_apagada: "la lectura de tu cuenta está apagada",
  sin_archivos: "no se encontraron los archivos de tu cuenta en este equipo",
  json_ilegible: "el archivo de tu cuenta no se pudo interpretar",
};

/** El aviso del agente de mantenimiento y despliegue (regla 9).
 *  `allow_opus_for_run` devuelve false para ese agente, así que un modelo de
 *  tier alto se degrada en silencio JUSTO ahí. Antes era invisible. */
const AVISO_DESPLIEGUE =
  "el agente de mantenimiento y despliegue nunca usa modelos de tier alto, aunque los elijas";

const ES_TIER_ALTO = (id: string) => /opus|fable/i.test(id);

export function describirOrigenCatalogo(
  res: ModelCatalogResponse | null | undefined,
  runtime: string,
): AvisoCatalogo {
  // Regla 1 — sin respuesta.
  if (!res) {
    return {
      nivel: "respaldo",
      texto: "Lista de respaldo: no se pudo consultar el catálogo de modelos.",
      detalle: "",
    };
  }

  // Regla 2 — la respuesta dice que no.
  if (res.ok === false) {
    return {
      nivel: "respaldo",
      texto: "Lista de respaldo: no se pudo consultar el catálogo de modelos.",
      detalle: res.reason ? String(res.reason) : "",
    };
  }

  // Regla 3 — se usó el respaldo de emergencia; se NOMBRA el motivo.
  if (res.fallback_used === true) {
    const motivo = res.error ? String(res.error) : "";
    return {
      nivel: "respaldo",
      texto:
        "Lista de respaldo: no se pudo leer el catálogo de modelos" +
        (motivo ? ` (${motivo}).` : "."),
      detalle: motivo,
    };
  }

  const bloque = (res.runtimes || {})[
    runtime as keyof typeof res.runtimes
  ];

  // Regla 10 — un motor que no está en la respuesta. No lanza.
  if (!bloque) {
    return {
      nivel: "respaldo",
      texto: "Lista de respaldo: este motor no vino en el catálogo de modelos.",
      detalle: "",
    };
  }

  // Regla 7 — error de introspección del motor de GitHub.                paridad-ok
  if (bloque.error) {                                                   // paridad-ok
    return {
      nivel: "parcial",
      texto: `La lista de este motor vino incompleta: ${String(bloque.error)}`,
      detalle: String(bloque.error),
    };
  }

  // Regla 6 — `cuenta` AUSENTE (el caso real de los otros dos motores) o un
  // motor que no es el de Claude Code. NO APLICAR NO ES UN PROBLEMA.
  const cuenta = bloque.cuenta;
  if (runtime !== "claude_code_cli" || !cuenta) return OK;

  // Regla 9 — si el motor ofrece algún id de tier alto, el detalle lo avisa.
  const hayTierAlto = (bloque.models || []).some((m) => ES_TIER_ALTO(m.id || ""));
  const detalleDespliegue = hayTierAlto ? AVISO_DESPLIEGUE : "";

  // Regla 5 — la cuenta no se pudo leer.
  if (cuenta.disponible === false) {
    const porQue = MOTIVO_CUENTA[cuenta.motivo] || cuenta.motivo || "no se pudo leer";
    return {
      nivel: "parcial",
      texto: `Lista de fábrica: ${porQue}.`,
      detalle: detalleDespliegue,
    };
  }

  // Regla 8 — hay descartes: se EXPLICAN, no se esconden.
  const omitidos = cuenta.omitidos || [];
  if (omitidos.length > 0) {
    const detalle = omitidos
      .map((o) => `${o.id}: ${MOTIVO_EN_CASTELLANO[o.motivo] || o.motivo}`)
      .join(" · ");
    return {
      nivel: "parcial",
      texto: `Tu cuenta usa ${omitidos.length} modelo(s) que Stacky no ofrece.`,
      detalle: detalleDespliegue ? `${detalle} — ${detalleDespliegue}` : detalle,
    };
  }

  // Regla 4 — todo salió bien: no se molesta al operador.
  return OK;
}
