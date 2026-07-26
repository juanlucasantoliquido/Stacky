import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { PipelineInventory } from "../../api/endpoints";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";
import { Button, SectionHeader, Skeleton } from "../ui";
import LoadErrorState from "../LoadErrorState";
import {
  categoryLabel,
  emptyStateMessage,
  filterEntries,
  mismatchHint,
  statusLabel,
  summarize,
  triggerLabel,
  truncationNotices,
  unavailableSources,
  type InventoryEntry,
  type InventoryPayload,
  type Tone,
} from "../../devops/pipelineInventoryModel";
import styles from "./PipelineInventorySection.module.css";

/**
 * Plan 246 F5 — Inventario vivo de pipelines: todas las del proyecto (registradas
 * en el proveedor + las que solo existen como YAML en el repo), en una sola lista.
 *
 * READ-ONLY absoluto: no crea, no edita y no lanza nada. NO sondea: el unico
 * refetch es el boton "Actualizar", accion explicita del operador.
 *
 * Toda la logica de etiquetas vive en el modelo puro `pipelineInventoryModel.ts`
 * (con tests); este archivo solo pinta. El estilado va por el .module.css: este
 * componente no declara atributos de estilo en linea.
 */

const TONE_CLASS: Record<Tone, string> = {
  ok: styles.toneOk,
  bad: styles.toneBad,
  warn: styles.toneWarn,
  faint: styles.toneFaint,
};

function Row({ entry }: { entry: InventoryEntry }) {
  const estado = statusLabel(entry.last_run);
  const categoria = categoryLabel(entry.category);
  const pista = mismatchHint(entry);
  return (
    <>
      <tr>
        <td className={TONE_CLASS[categoria.tone]} title={categoria.hint}>
          {categoria.text}
        </td>
        <td>{entry.name || "(sin nombre)"}</td>
        <td>{entry.provider}</td>
        <td className={styles.mono}>{entry.yaml_path || "—"}</td>
        <td>{entry.default_branch || "—"}</td>
        <td className={TONE_CLASS[estado.tone]}>
          {entry.last_run.web_url ? (
            <a href={entry.last_run.web_url} target="_blank" rel="noreferrer">
              {estado.text}
            </a>
          ) : (
            estado.text
          )}
        </td>
        <td>{triggerLabel(entry.trigger)}</td>
      </tr>
      {pista ? (
        <tr className={styles.hintRow}>
          <td colSpan={7}>
            <span className={styles.hint}>{pista}</span>
          </td>
        </tr>
      ) : null}
    </>
  );
}

export function PipelineInventorySection({ ctx }: { ctx: DevOpsSectionContext }) {
  void ctx;
  const [filtro, setFiltro] = useState("");

  const query = useQuery({
    queryKey: ["pipeline-inventory"],
    queryFn: () => PipelineInventory.list(null, false),
    retry: false,
  });

  const payload = (query.data as InventoryPayload | undefined) ?? null;
  const entradas = useMemo(
    () => filterEntries(payload?.pipelines ?? [], filtro),
    [payload, filtro],
  );
  const caidas = unavailableSources(payload);
  const avisos = truncationNotices(payload);
  const vacio = emptyStateMessage(payload, entradas.length);

  return (
    <div className={styles.section}>
      <SectionHeader
        title="Inventario de pipelines"
        subtitle="Registradas en el proveedor y YAML del repo, en una sola lista. Solo lectura."
      />

      <div className={styles.toolbar}>
        <input
          className={styles.filter}
          placeholder="Filtrar por nombre, ruta o proveedor"
          value={filtro}
          onChange={(e) => setFiltro(e.target.value)}
          aria-label="Filtrar pipelines"
        />
        <span className={styles.summary}>{summarize(payload)}</span>
        <span className={styles.spacer} />
        <Button
          variant="secondary"
          onClick={() => {
            void query.refetch();
          }}
          disabled={query.isFetching}
        >
          {query.isFetching ? "Actualizando…" : "Actualizar"}
        </Button>
      </div>

      {caidas.length > 0 ? (
        <div className={styles.banner}>
          <span className={styles.bannerTitle}>Fuentes que no se pudieron consultar</span>
          {caidas.map((s) => (
            <span key={s.id} className={styles.bannerLine}>
              {s.id}: {s.reason} {s.workaround ? `— ${s.workaround}` : ""}
            </span>
          ))}
        </div>
      ) : null}

      {avisos.length > 0 ? (
        <ul className={styles.notices}>
          {avisos.map((a) => (
            <li key={a} className={styles.noticeItem}>
              {a}
            </li>
          ))}
        </ul>
      ) : null}

      {query.isLoading ? <Skeleton lines={4} /> : null}
      {query.isError ? (
        <LoadErrorState
          what="el inventario de pipelines"
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : null}

      {!query.isLoading && !query.isError ? (
        entradas.length === 0 ? (
          <div className={styles.empty}>{vacio}</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Estado</th>
                  <th>Nombre</th>
                  <th>Proveedor</th>
                  <th>Ruta del YAML</th>
                  <th>Rama</th>
                  <th>Ultima corrida</th>
                  <th>Trigger</th>
                </tr>
              </thead>
              <tbody>
                {entradas.map((e) => (
                  <Row key={e.key} entry={e} />
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}
    </div>
  );
}

export default PipelineInventorySection;
