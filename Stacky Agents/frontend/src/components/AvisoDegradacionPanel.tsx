/**
 * AvisoDegradacionPanel.tsx — Plan 290 F4.
 *
 * Muestra qué capacidades decidió Stacky NO ejecutar en esta corrida porque el
 * tracker del proyecto no las tiene. NO es una lista de errores: la degradación
 * es la conducta correcta, lo que faltaba era que quedara dicha.
 *
 * Bloque presentacional puro. Sin datos devuelve `null`: no se monta, no ocupa
 * espacio y no cambia el layout de ninguna ejecución existente ni histórica —
 * la ausencia de `metadata.capability_degraded` es el estado válido de todas.
 *
 * Toda la lógica vive en `services/capabilityDegradedModel.ts` (`.ts` puro, con
 * tests de vitest): acá solo se pinta.
 */
import {
  agruparPorProveedor,
  etiquetaDeCapacidad,
  leerDegradaciones,
} from "../services/capabilityDegradedModel";
import styles from "./AvisoDegradacionPanel.module.css";

interface Props {
  metadata?: Record<string, unknown> | null;
}

export default function AvisoDegradacionPanel({ metadata }: Props) {
  const items = leerDegradaciones(metadata);
  if (items.length === 0) return null;

  return (
    <section className={styles.block}>
      <h4 className={styles.title}>Capacidades no disponibles en este tracker</h4>
      <p className={styles.intro}>
        Stacky salteó estos pasos a propósito porque el tracker del proyecto no
        expone esa capacidad. No es un error: es lo que decidió, y por qué.
      </p>

      {agruparPorProveedor(items).map(([proveedor, delProveedor]) => (
        <div key={proveedor} className={styles.grupo}>
          <span className={styles.proveedor}>{proveedor}</span>
          <ul className={styles.items}>
            {delProveedor.map((d, i) => (
              <li key={`${d.capability}-${d.site}-${i}`} className={styles.item}>
                {/* Marca NO cromática: el color solo no puede ser el único
                    portador de información. */}
                <span className={styles.marca} aria-hidden="true">
                  ⚠
                </span>
                <span className={styles.texto}>
                  <span className={styles.capacidad}>
                    {etiquetaDeCapacidad(d.capability)}
                  </span>
                  <span className={styles.motivo}>
                    {d.reason}
                    {d.site ? (
                      <>
                        {" "}
                        <span className={styles.sitio}>({d.site})</span>
                      </>
                    ) : null}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
