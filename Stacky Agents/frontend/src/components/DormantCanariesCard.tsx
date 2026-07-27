/**
 * DormantCanariesCard.tsx — Plan 255 F6: "Mecanismos dormidos" en Diagnóstico.
 *
 * Lo inverso a una huella de regresión: alarma cuando un patrón BUENO deja de
 * aparecer. El resume estuvo 9 días muerto con las flags en ON porque Stacky
 * medía que las cosas fallaran, no que hubieran funcionado.
 *
 * AVISA, NUNCA ARREGLA: cada fila trae un `hint` de qué mirar, jamás una acción
 * automática. `apagado` (lo apagó el operador) y `sin_datos` (no hay registro
 * suficiente) se muestran en gris y NO son alarmas — esa distinción es lo que
 * evita que la card se vuelva ruido.
 *
 * READ-ONLY. Se auto-oculta con 404 si la flag está apagada.
 */
import { useEffect, useState } from "react";
import { BellOff } from "lucide-react";
import { DormantCanaries, type DormantCanaryRow } from "../api/endpoints";
import styles from "./DormantCanariesCard.module.css";

type Status = "checking-visibility" | "running" | "done";

const STATUS_LABEL: Record<string, string> = {
  ok: "activo",
  dormido: "dormido",
  apagado: "apagado por vos",
  sin_datos: "sin registro suficiente",
};

function claseDe(estado: string): string {
  if (estado === "dormido") return styles.dormido;
  if (estado === "ok") return styles.ok;
  return styles.neutro;
}

function detalle(row: DormantCanaryRow): string {
  if (row.status === "apagado") return "No se espera actividad: está apagado a propósito.";
  if (row.status === "sin_datos") return "No hay registro suficiente para afirmar nada.";
  if (row.status === "ok") {
    const d = row.days_silent ?? 0;
    return d === 0 ? "Funcionó hoy." : `Última vez que funcionó: hace ${d} día(s).`;
  }
  return `Sin una sola señal de éxito en ${row.max_silent_days} día(s).`;
}

export default function DormantCanariesCard() {
  const [status, setStatus] = useState<Status>("checking-visibility");
  const [hidden, setHidden] = useState(false);
  const [rows, setRows] = useState<DormantCanaryRow[]>([]);

  useEffect(() => {
    let cancelled = false;
    DormantCanaries.get()
      .then((res) => {
        if (cancelled) return;
        setRows(res.canaries ?? []);
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
    DormantCanaries.get()
      .then((res) => {
        setRows(res.canaries ?? []);
        setStatus("done");
      })
      .catch(() => setStatus("done"));
  };

  const dormidos = rows.filter((r) => r.status === "dormido").length;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <BellOff size={16} />
          Mecanismos dormidos
        </h2>
        <button className={styles.runBtn} onClick={refresh} disabled={status === "running"}>
          {status === "running" ? "Revisando…" : "Revisar ahora"}
        </button>
      </div>

      {dormidos === 0 ? (
        <p className={styles.okLine}>
          ✓ Ningún mecanismo vigilado dejó de dar señales de haber funcionado.
        </p>
      ) : (
        <p className={styles.summary}>
          {dormidos} mecanismo{dormidos === 1 ? "" : "s"} lleva{dormidos === 1 ? "" : "n"} días
          sin una sola señal de éxito, con el interruptor encendido.
        </p>
      )}

      <ul className={styles.rowList}>
        {rows.map((row) => (
          <li key={row.id}>
            <span className={`${styles.badge} ${claseDe(row.status)}`}>
              {STATUS_LABEL[row.status] ?? row.status}
            </span>
            <div className={styles.rowBody}>
              <strong className={styles.label}>{row.label}</strong>
              <span className={styles.detalle}>{detalle(row)}</span>
              {row.status === "dormido" && <span className={styles.hint}>{row.hint}</span>}
            </div>
          </li>
        ))}
      </ul>

      <p className={styles.muted}>
        Solo lectura: esta revisión no reintenta, no vuelve a encender nada y no cambia
        ninguna configuración. Vos decidís qué hacer con cada línea.
      </p>
    </div>
  );
}
