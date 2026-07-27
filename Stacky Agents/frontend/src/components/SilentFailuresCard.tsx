/**
 * SilentFailuresCard.tsx — Plan 255 F1: "Fallos silenciados" en Diagnóstico.
 *
 * El backend tiene 166 puntos donde un fallo se atrapa y no deja rastro. Esta
 * card no los arregla: los hace CONTABLES, que es el paso previo obligatorio.
 *
 * REGLA ANTI-CONCLUSIÓN (va en el título y en el tooltip, no solo en el código):
 * el contador vive en memoria y el servicio reinicia varias veces por día, así
 * que la card SIEMPRE declara su ventana. Un cero NO prueba que un punto sea
 * inerte: solo que no se disparó desde el último arranque. Nunca se retira
 * instrumentación basándose en un cero.
 *
 * READ-ONLY. La card decide su propia visibilidad con un fetch de montaje (404
 * con la flag apagada → la card no existe).
 */
import { useEffect, useState } from "react";
import { EyeOff } from "lucide-react";
import { SilentFailures, type SilentFailuresResponse } from "../api/endpoints";
import { formatDuration, formatTime } from "../services/format";
import styles from "./SilentFailuresCard.module.css";

type Status = "checking-visibility" | "idle" | "running" | "done";

/** La ventana viene en segundos; el formateador canónico trabaja en ms. */
function fmtVentana(segundos: number): string {
  if (!Number.isFinite(segundos) || segundos < 0) return "desconocida";
  return formatDuration(segundos * 1000);
}

export default function SilentFailuresCard() {
  const [status, setStatus] = useState<Status>("checking-visibility");
  const [hidden, setHidden] = useState(false);
  const [report, setReport] = useState<SilentFailuresResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    SilentFailures.get()
      .then((res) => {
        if (cancelled) return;
        setReport(res);
        setStatus("done");
      })
      .catch(() => {
        if (!cancelled) setHidden(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (hidden || status === "checking-visibility") return null;

  const refresh = () => {
    setStatus("running");
    SilentFailures.get()
      .then((res) => {
        setReport(res);
        setStatus("done");
      })
      .catch(() => setStatus("done"));
  };

  const rows = report?.rows ?? [];
  const ventana = report?.window;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <EyeOff size={16} />
          Fallos silenciados
          {ventana && (
            <span className={styles.ventana}>
              — ventana: {fmtVentana(ventana.window_seconds)} (desde el último arranque)
            </span>
          )}
        </h2>
        <button className={styles.runBtn} onClick={refresh} disabled={status === "running"}>
          {status === "running" ? "Revisando…" : "Revisar ahora"}
        </button>
      </div>

      {rows.length === 0 ? (
        <p className={styles.okLine}>
          ✓ Ningún punto del sistema se tragó un fallo en esta ventana.
        </p>
      ) : (
        <ul className={styles.rowList}>
          {rows.map((row) => (
            <li key={row.site}>
              <span className={styles.count}>{row.count}</span>
              <span className={styles.site}>{row.site}</span>
              <em className={styles.meta}>
                {row.last_exc_type ?? "sin tipo"} · {formatTime(row.last_seen)}
              </em>
            </li>
          ))}
        </ul>
      )}

      <p
        className={styles.muted}
        title={
          "Un cero NO prueba que ese punto sea inerte: solo que no se disparó en esta " +
          "ventana. El contador vive en memoria y se pierde en cada reinicio. Sirve para " +
          "priorizar qué investigar, nunca para descartar."
        }
      >
        Un cero no prueba que un punto sea inerte: solo que no se disparó desde el
        último arranque. Sirve para priorizar, no para descartar.
      </p>
    </div>
  );
}
