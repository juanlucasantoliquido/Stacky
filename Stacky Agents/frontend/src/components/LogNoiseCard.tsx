/**
 * LogNoiseCard.tsx — Plan 257 F3: "Firmas de log más repetidas" en Diagnóstico.
 *
 * Con esta tarjeta, las 1016 ocurrencias de una sola firma habrían sido
 * visibles el PRIMER día, en la primera fila, en vez de sobrevivir dos días
 * escondidas entre miles de líneas.
 *
 * READ-ONLY y sin costo: el reporte sale de los contadores en memoria del
 * agrupador (`snapshot()`), no se vuelve a leer ni un archivo de disco, y
 * mirar NO resetea nada (el único que vuelca los contadores es el volcado
 * determinista del servicio).
 *
 * Si no hay firmas agrupadas, la tarjeta NO se renderiza: sin ruido visual
 * cuando todo está limpio.
 */
import { useEffect, useState } from "react";
import { Waves } from "lucide-react";
import { LogNoise } from "../api/endpoints";
import { formatDuration } from "../services/format";
import { buildLogNoiseRows, logNoiseLabel, type LogNoisePayload } from "./logNoiseModel";
import styles from "./LogNoiseCard.module.css";

export default function LogNoiseCard() {
  const [cargado, setCargado] = useState(false);
  const [refrescando, setRefrescando] = useState(false);
  const [payload, setPayload] = useState<LogNoisePayload | null>(null);

  const cargar = (marcarRefresco: boolean) => {
    if (marcarRefresco) setRefrescando(true);
    LogNoise.get()
      .then((res) => setPayload(res))
      .catch(() => setPayload(null))
      .finally(() => {
        setCargado(true);
        setRefrescando(false);
      });
  };

  useEffect(() => {
    let cancelado = false;
    LogNoise.get()
      .then((res) => {
        if (!cancelado) setPayload(res);
      })
      .catch(() => {
        if (!cancelado) setPayload(null);
      })
      .finally(() => {
        if (!cancelado) setCargado(true);
      });
    return () => {
      cancelado = true;
    };
  }, []);

  const filas = buildLogNoiseRows(payload);
  if (!cargado || filas.length === 0) return null;

  const ventana = payload?.window_s;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <Waves size={16} />
          Firmas de log más repetidas
          {ventana ? (
            <span className={styles.ventana}>
              — se agrupan las repeticiones de los últimos {formatDuration(ventana * 1000)}
            </span>
          ) : null}
        </h2>
        <button
          className={styles.runBtn}
          onClick={() => cargar(true)}
          disabled={refrescando}
        >
          {refrescando ? "Revisando…" : "Revisar ahora"}
        </button>
      </div>

      <ul className={styles.rowList}>
        {filas.map((fila) => (
          <li key={fila.signature}>
            <span className={styles.count}>{fila.suppressed}</span>
            <span className={styles.firma}>{logNoiseLabel(fila.signature)}</span>
            <em className={styles.meta}>
              {fila.logger} · {fila.level} · {fila.count} en total
            </em>
          </li>
        ))}
      </ul>

      <p
        className={styles.muted}
        title={
          "El número de la izquierda son las repeticiones agrupadas que todavía no se " +
          "volcaron al registro. Nada se pierde: el conteo se escribe siempre, al " +
          "reaparecer la firma o al volcarse por tiempo o al apagar el servicio."
        }
      >
        A la izquierda, las repeticiones agrupadas pendientes de volcar. Mirar esta
        lista no borra ningún contador.
      </p>
    </div>
  );
}
