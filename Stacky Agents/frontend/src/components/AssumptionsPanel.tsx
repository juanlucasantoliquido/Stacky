import { useState } from "react";

import { Executions } from "../api/endpoints";
import { Button, Textarea } from "./ui";
import styles from "./AssumptionsPanel.module.css";
import {
  badgeLabel,
  hasSomethingToShow,
  isUnbased,
  orderedForDisplay,
  overloadWarning,
  readAssumptions,
  statusLabel,
  type AssumptionDTO,
  type AssumptionsMetaDTO,
} from "./assumptionsModel";

/**
 * Plan 213 F5 — Los supuestos del analista, con confirmar/corregir en un click.
 *
 * Confirmar o corregir acá NO toca el tracker, NO mueve el ticket y NO relanza
 * nada. Lo que hace el sistema con esa decisión es devolvérsela al agente en la
 * corrida siguiente, con prioridad máxima (F6).
 *
 * Si no hubo supuestos, el panel no renderiza nada: cero ruido.
 */
export default function AssumptionsPanel({
  executionId,
  metadata,
  onUpdated,
}: {
  executionId: number;
  metadata: Record<string, unknown> | null | undefined;
  onUpdated?: (meta: AssumptionsMetaDTO) => void;
}) {
  const inicial = readAssumptions(metadata);
  const [meta, setMeta] = useState<AssumptionsMetaDTO | null>(inicial);
  const [editando, setEditando] = useState<number | null>(null);
  const [borrador, setBorrador] = useState("");
  const [guardando, setGuardando] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const actual = meta ?? inicial;
  if (!hasSomethingToShow(actual)) return null;

  async function aplicar(index: number, status: string, correction?: string) {
    setGuardando(index);
    setError(null);
    try {
      const r = await Executions.patchAssumptions(executionId, [
        { index, status, correction },
      ]);
      const nuevo = r.assumptions as AssumptionsMetaDTO;
      setMeta(nuevo);
      onUpdated?.(nuevo);
      setEditando(null);
      setBorrador("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar la decisión.");
    } finally {
      setGuardando(null);
    }
  }

  const aviso = overloadWarning(actual);
  const filas = orderedForDisplay(actual?.items);

  return (
    <div className={styles.panel}>
      <span className={styles.badge}>{badgeLabel(actual)}</span>
      {aviso && <p className={styles.overload}>{aviso}</p>}
      {error && <p className={styles.overload}>{error}</p>}

      <ul className={styles.list}>
        {filas.map(({ item, index }) => (
          <li
            key={index}
            className={`${styles.item} ${item.impact === "high" ? styles.itemHigh : ""}`}
          >
            <p className={styles.text}>{item.text}</p>
            <p className={`${styles.basis} ${isUnbased(item) ? styles.unbased : ""}`}>
              {isUnbased(item) ? "sin respaldo declarado" : `base: ${item.basis}`}
            </p>
            <span className={styles.status}>
              {statusLabel(item.status)}
              {item.impact === "high" ? " · impacto alto" : ""}
            </span>
            {item.correction && (
              <p className={styles.correction}>Tu corrección: {item.correction}</p>
            )}

            {editando === index ? (
              <div className={styles.actions}>
                <Textarea
                  value={borrador}
                  onChange={(e) => setBorrador(e.target.value)}
                  placeholder="Escribí la interpretación correcta…"
                  rows={2}
                />
                <Button
                  size="sm"
                  variant="primary"
                  disabled={!borrador.trim() || guardando === index}
                  onClick={() => aplicar(index, "corrected", borrador.trim())}
                >
                  Guardar corrección
                </Button>
                <Button size="sm" onClick={() => setEditando(null)}>
                  Cancelar
                </Button>
              </div>
            ) : (
              <div className={styles.actions}>
                <Button
                  size="sm"
                  disabled={guardando === index}
                  onClick={() => aplicar(index, "confirmed")}
                >
                  ✔ Confirmar
                </Button>
                <Button
                  size="sm"
                  disabled={guardando === index}
                  onClick={() => {
                    setEditando(index);
                    setBorrador(item.correction ?? "");
                  }}
                >
                  ✎ Corregir
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {(actual?.pending?.length ?? 0) > 0 && (
        <>
          <span className={styles.badge}>Datos que el agente no pudo inferir</span>
          <ul className={styles.pendingList}>
            {actual!.pending!.map((p, i) => (
              <li key={i}>
                {p.text}
                {p.needs ? ` — necesita: ${p.needs}` : ""}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export type { AssumptionDTO };
