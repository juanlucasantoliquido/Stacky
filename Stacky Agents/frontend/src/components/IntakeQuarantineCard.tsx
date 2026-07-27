/**
 * IntakeQuarantineCard.tsx — Plan 256 F3/F4: "Artefactos en cuarentena".
 *
 * El watcher venia apartando artefactos con una razon completa y accionable
 * desde hacia 11 dias, pero esa razon solo vivia en un archivo de registro de
 * 4 MB. Esta tarjeta la trae a donde el operador ya mira, con la antiguedad al
 * frente y los dos botones que cierran el ciclo.
 *
 * HUMAN IN THE LOOP: la tarjeta AVISA; nunca reintenta ni descarta sola.
 *  - Reintentar es no destructivo (un clic, sin confirmacion).
 *  - Descartar NO borra ni modifica el artefacto: marca una ficha al lado. Aun
 *    asi pide confirmacion explicita y vive detras de una flag apagada por
 *    defecto, porque desde la pantalla no se revierte.
 *
 * La razon se muestra COMPLETA y sin truncar: truncarla fue exactamente el bug.
 * Se auto-oculta si no hay nada apartado o si la superficie esta apagada.
 */
import { useCallback, useEffect, useState } from "react";
import { PackageX } from "lucide-react";

import { IntakeQuarantine } from "../api/endpoints";
import {
  formatAge,
  shouldRenderCard,
  sortByAgeDesc,
  type QuarantineItem,
} from "../incidents/quarantineModel";
import styles from "./IntakeQuarantineCard.module.css";

type Status = "checking-visibility" | "idle" | "working";

export default function IntakeQuarantineCard() {
  const [status, setStatus] = useState<Status>("checking-visibility");
  const [hidden, setHidden] = useState(false);
  const [items, setItems] = useState<QuarantineItem[]>([]);
  const [discardEnabled, setDiscardEnabled] = useState(false);
  /** path -> identificador de confirmacion pendiente del descarte. */
  const [pendingConfirm, setPendingConfirm] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<Record<string, string>>({});

  const load = useCallback((first: boolean) => {
    return IntakeQuarantine.get()
      .then((res) => {
        if (res.enabled === false) {
          setHidden(true);
          return;
        }
        setItems(res.items ?? []);
        setDiscardEnabled(Boolean(res.discard_enabled));
        setStatus("idle");
      })
      .catch(() => {
        if (first) setHidden(true);
        else setStatus("idle");
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    IntakeQuarantine.get()
      .then((res) => {
        if (cancelled) return;
        if (res.enabled === false) {
          setHidden(true);
          return;
        }
        setItems(res.items ?? []);
        setDiscardEnabled(Boolean(res.discard_enabled));
        setStatus("idle");
      })
      .catch(() => {
        if (!cancelled) setHidden(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (hidden || status === "checking-visibility") return null;
  if (!shouldRenderCard(items.length)) return null;

  const ahora = new Date().toISOString();
  const ordenados = sortByAgeDesc(items);

  const onRetry = (path: string) => {
    setStatus("working");
    IntakeQuarantine.retry(path)
      .then((res) => {
        setFeedback((prev) => ({
          ...prev,
          [path]:
            res.status === 200
              ? "Se quito de la cuarentena. El vigilante lo va a reintentar en el proximo repaso."
              : `No se pudo reintentar (${res.status}).`,
        }));
        return load(false);
      })
      .finally(() => setStatus("idle"));
  };

  const onDiscardAsk = (path: string) => {
    setStatus("working");
    IntakeQuarantine.discard(path)
      .then((res) => {
        const token = typeof res.body.confirm_token === "string" ? res.body.confirm_token : "";
        if (res.status === 409 && token) {
          setPendingConfirm((prev) => ({ ...prev, [path]: token }));
        } else {
          setFeedback((prev) => ({ ...prev, [path]: `No se pudo preparar el descarte (${res.status}).` }));
        }
      })
      .finally(() => setStatus("idle"));
  };

  const onDiscardConfirm = (path: string) => {
    const token = pendingConfirm[path];
    if (!token) return;
    setStatus("working");
    IntakeQuarantine.discard(path, token)
      .then((res) => {
        setPendingConfirm((prev) => {
          const next = { ...prev };
          delete next[path];
          return next;
        });
        setFeedback((prev) => ({
          ...prev,
          [path]:
            res.status === 200
              ? "Marcado como descartado. El archivo sigue intacto en el disco."
              : `No se pudo descartar (${res.status}). Sigue en la lista.`,
        }));
        return load(false);
      })
      .finally(() => setStatus("idle"));
  };

  const onDiscardCancel = (path: string) => {
    setPendingConfirm((prev) => {
      const next = { ...prev };
      delete next[path];
      return next;
    });
  };

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <PackageX size={16} />
          Artefactos en cuarentena
        </h2>
        <button
          className={styles.refreshBtn}
          onClick={() => {
            setStatus("working");
            load(false).finally(() => setStatus("idle"));
          }}
          disabled={status === "working"}
        >
          {status === "working" ? "Revisando…" : "Revisar ahora"}
        </button>
      </div>

      <p className={styles.summary}>
        {ordenados.length} archivo{ordenados.length === 1 ? "" : "s"} entregado
        {ordenados.length === 1 ? "" : "s"} por un agente qued
        {ordenados.length === 1 ? "ó" : "aron"} apartado
        {ordenados.length === 1 ? "" : "s"} y no entr{ordenados.length === 1 ? "ó" : "aron"} al
        tablero. Acá está el motivo exacto de cada uno.
      </p>

      <ul className={styles.rowList}>
        {ordenados.map((item) => (
          <li key={item.path}>
            <div className={styles.rowHead}>
              <span className={styles.fileName}>{item.file_name}</span>
              <span
                className={`${styles.badge} ${item.age_days >= 1 ? styles.badgeStuck : ""}`}
              >
                {formatAge(item.first_seen, ahora)}
              </span>
              <span className={styles.badge}>{item.cause_code}</span>
              {item.occurrences > 1 && (
                <span className={styles.badge}>visto {item.occurrences} veces</span>
              )}
              {item.has_original_backup && (
                <span className={styles.badge}>hay copia del original</span>
              )}
              {item.discarded && <span className={styles.badge}>descartado</span>}
            </div>

            <p className={styles.reason}>{item.reason}</p>
            <span className={styles.path}>{item.path}</span>

            <div className={styles.actions}>
              <button
                className={styles.actionBtn}
                onClick={() => onRetry(item.path)}
                disabled={status === "working" || !item.retryable}
                title={
                  item.retryable
                    ? "Reintenta la validación; no corrige el artefacto."
                    : "Primero hay que resolver el problema de disco que impidió guardar la copia."
                }
              >
                Reintentar
              </button>

              {discardEnabled && !item.discarded && !pendingConfirm[item.path] && (
                <button
                  className={styles.actionBtn}
                  onClick={() => onDiscardAsk(item.path)}
                  disabled={status === "working"}
                  title="Deja de reintentarlo. El archivo no se toca."
                >
                  Descartar
                </button>
              )}

              {feedback[item.path] && (
                <span className={styles.feedback}>{feedback[item.path]}</span>
              )}
            </div>

            {pendingConfirm[item.path] && (
              <div className={styles.confirmBox}>
                <span>
                  El artefacto queda intacto en disco. Solo se marca como descartado y el
                  vigilante deja de reintentarlo. Para revertirlo hay que borrar la ficha a
                  mano.
                </span>
                <div className={styles.actions}>
                  <button
                    className={styles.actionBtn}
                    onClick={() => onDiscardConfirm(item.path)}
                    disabled={status === "working"}
                  >
                    Sí, descartar
                  </button>
                  <button
                    className={styles.actionBtn}
                    onClick={() => onDiscardCancel(item.path)}
                    disabled={status === "working"}
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>

      <p className={styles.muted}>
        Stacky no descarta trabajo por su cuenta: acá solo se muestra lo que quedó apartado
        y por qué. Reintentar vuelve a validar el archivo tal cual está; no lo corrige.
      </p>
    </div>
  );
}
