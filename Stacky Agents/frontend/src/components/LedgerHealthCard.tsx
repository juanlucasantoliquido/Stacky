/**
 * LedgerHealthCard.tsx — Plan 258 F3/F4: "Salud de ledgers" en Diagnóstico.
 *
 * Los archivos de registro deberían darle al operador visibilidad de lo que la
 * interfaz no muestra. Medido antes de este plan: `ci_runs.jsonl` tenía 8 de 8
 * líneas de fixture de test y `env_applies.jsonl` 10 de 10 escritas por pytest.
 * No eran una fuente de verdad: eran archivos mezclados. Con esta tarjeta eso
 * se ve el primer día, no seis meses después auditando a mano.
 *
 * READ-ONLY salvo el botón de limpieza, que es la ÚNICA acción destructiva del
 * plan y va en dos pasos: el primer pedido vuelve con el conteo exacto y una
 * confirmación de un solo uso; el segundo borra. No se usa el diálogo nativo
 * del navegador: el aviso se pinta acá con la cifra a la vista.
 *
 * Si no hay líneas de prueba ni corridas reales sin cerrar, la tarjeta NO se
 * renderiza: sin ruido visual cuando todo está limpio.
 */
import { useEffect, useState } from "react";
import { FileCheck2 } from "lucide-react";
import { Ledgers } from "../api/endpoints";
import {
  buildLedgerRows,
  hayAlgoQueReportar,
  ledgerLabel,
  resumenDeSalud,
  textoDeLimpieza,
  type LedgerHealthPayload,
  type LedgerHealthRow,
} from "./ledgerHealthModel";
import styles from "./LedgerHealthCard.module.css";

interface Pendiente {
  ledger: string;
  token: string;
  mensaje: string;
}

export default function LedgerHealthCard() {
  const [cargado, setCargado] = useState(false);
  const [refrescando, setRefrescando] = useState(false);
  const [payload, setPayload] = useState<LedgerHealthPayload | null>(null);
  const [pendiente, setPendiente] = useState<Pendiente | null>(null);
  const [trabajando, setTrabajando] = useState(false);
  const [resultado, setResultado] = useState<string | null>(null);

  const cargar = (marcarRefresco: boolean) => {
    if (marcarRefresco) setRefrescando(true);
    Ledgers.health()
      .then((res) => setPayload(res))
      .catch(() => setPayload(null))
      .finally(() => {
        setCargado(true);
        setRefrescando(false);
      });
  };

  useEffect(() => {
    let cancelado = false;
    Ledgers.health()
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

  // Paso 1: pedir la limpieza sin confirmación. El servicio responde con el
  // conteo exacto y una confirmación de un solo uso; NO borra nada todavía.
  const pedirLimpieza = (fila: LedgerHealthRow) => {
    setTrabajando(true);
    setResultado(null);
    Ledgers.purge(fila.name, null)
      .then((res) => {
        if (res.confirm_token) {
          setPendiente({
            ledger: fila.name,
            token: res.confirm_token,
            mensaje: res.message || textoDeLimpieza(fila),
          });
        } else {
          setResultado("No hay líneas de prueba para limpiar en este archivo.");
        }
      })
      .catch(() => setResultado("No se pudo preparar la limpieza."))
      .finally(() => setTrabajando(false));
  };

  // Paso 2: el operador ya vio la cifra. Ahora sí.
  const limpiarDeVerdad = () => {
    if (!pendiente) return;
    setTrabajando(true);
    Ledgers.purge(pendiente.ledger, pendiente.token)
      .then((res) => {
        setResultado(
          res.deleted
            ? `Se eliminaron ${res.deleted} líneas de prueba. Copia guardada.`
            : res.detail || "No se eliminó nada."
        );
        setPendiente(null);
        cargar(true);
      })
      .catch(() => setResultado("No se pudo completar la limpieza."))
      .finally(() => setTrabajando(false));
  };

  const filas = buildLedgerRows(payload);
  if (!cargado || !hayAlgoQueReportar(payload)) return null;

  const huerfanos = payload?.orphans ?? [];
  const purgaHabilitada = payload?.purge_enabled === true;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <FileCheck2 size={16} />
          Salud de ledgers
          <span className={styles.resumen}>— {resumenDeSalud(payload)}</span>
        </h2>
        <button
          className={styles.runBtn}
          onClick={() => cargar(true)}
          disabled={refrescando || trabajando}
        >
          {refrescando ? "Revisando…" : "Revisar ahora"}
        </button>
      </div>

      <ul className={styles.rowList}>
        {filas.map((fila) => (
          <li key={fila.name}>
            <span className={styles.marcaTest}>{fila.test}</span>
            <span className={styles.nombre}>{ledgerLabel(fila.name)}</span>
            <em className={styles.conteos}>
              {fila.total} en total · {fila.prod} reales · {fila.unknown} sin marca
            </em>
            {purgaHabilitada && fila.purgeable && fila.deletable > 0 ? (
              <button
                className={styles.purgeBtn}
                onClick={() => pedirLimpieza(fila)}
                disabled={trabajando}
              >
                Limpiar {fila.deletable}
              </button>
            ) : null}

            {pendiente && pendiente.ledger === fila.name ? (
              <div className={styles.aviso}>
                {pendiente.mensaje}
                <div className={styles.avisoAcciones}>
                  <button
                    className={styles.purgeBtn}
                    onClick={limpiarDeVerdad}
                    disabled={trabajando}
                  >
                    Sí, eliminar
                  </button>
                  <button
                    className={styles.purgeBtn}
                    onClick={() => setPendiente(null)}
                    disabled={trabajando}
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      {huerfanos.length > 0 ? (
        <>
          <h3 className={styles.subtitulo}>Corridas reales que nunca cerraron</h3>
          <ul className={styles.huerfanos}>
            {huerfanos.map((h) => (
              <li key={`${h.project}-${h.pipeline_id}`}>
                {h.project} · {h.pipeline_id} · hace {h.age_hours} h sin desenlace
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {resultado ? <p className={styles.muted}>{resultado}</p> : null}

      <p
        className={styles.muted}
        title={
          "A la izquierda, cuántas líneas escribió una prueba. Las de procedencia " +
          "desconocida son las anteriores al sello: no se pueden afirmar como reales, " +
          "así que no se cuentan como problema ni se borran nunca."
        }
      >
        A la izquierda, las líneas que escribió una prueba. Las de procedencia
        desconocida nunca se borran.
      </p>
    </div>
  );
}
