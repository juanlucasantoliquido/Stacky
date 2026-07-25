import { Fragment } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitCompareArrows } from "lucide-react";
import { api } from "../api/client";
import {
  groupByDomain,
  statusLabel,
  statusMark,
  summarize,
  type CapabilityRow,
  type ParityMatrixResponse,
} from "../services/parityMatrixModel";
import styles from "./ParityMatrixPanel.module.css";

/**
 * Panel de paridad ADO ↔ GitLab — Plan 218 F8.
 *
 * Cierra el lazo human-in-the-loop: el operador ve ANTES de empezar qué puede y qué
 * no puede hacer su tracker, en vez de descubrirlo por un error a mitad de un flujo.
 *
 * Con STACKY_PROVIDER_PARITY_ENABLED=false el endpoint devuelve 404 y el panel
 * simplemente no se monta (rollback completo del 218 en un click).
 */

const STATUS_CLASS: Record<string, string> = {
  full: styles.statusFull,
  partial: styles.statusPartial,
  "n/a": styles.statusNa,
};

function StatusCell({ cap }: { cap: CapabilityRow }) {
  const clase = STATUS_CLASS[cap.status] ?? styles.statusAbsent;
  return (
    <span className={clase}>
      <span className={styles.mark} aria-hidden="true">
        {statusMark(cap.status)}
      </span>
      {statusLabel(cap.status)}
      {!cap.enabled && cap.status !== "absent" && cap.status !== "n/a" ? (
        <span className={styles.disabled}> · apagada para este proyecto</span>
      ) : null}
    </span>
  );
}

export default function ParityMatrixPanel({ project }: { project?: string }) {
  const query = useQuery({
    queryKey: ["parity-matrix", project ?? ""],
    queryFn: () =>
      api.get<ParityMatrixResponse>(
        `/api/parity/matrix${project ? `?project=${encodeURIComponent(project)}` : ""}`,
      ),
    retry: false,
  });

  // 404 = la flag maestra está apagada: el panel no existe. No es un error a mostrar.
  if (query.isError || (!query.isLoading && !query.data)) return null;

  const data = query.data;
  const capacidades = data?.capabilities ?? [];
  const resumen = summarize(capacidades);
  const grupos = groupByDomain(capacidades);

  return (
    <section className={styles.panel} aria-label="Paridad de proveedores">
      <header className={styles.header}>
        <div className={styles.title}>
          <GitCompareArrows size={18} aria-hidden="true" />
          <span>Paridad del tracker</span>
          {data ? <span className={styles.provider}>{data.provider}</span> : null}
        </div>
        <span className={styles.subtitle}>
          Qué soporta el tracker de este proyecto, y con qué pérdida cuando es parcial.
        </span>
      </header>

      {query.isLoading ? (
        <p className={styles.empty}>Cargando capacidades…</p>
      ) : (
        <>
          <div className={styles.summary}>
            <span className={styles.summaryItem}>
              <span className={styles.summaryCount}>{resumen.full}</span> completas
            </span>
            <span className={styles.summaryItem}>
              <span className={styles.summaryCount}>{resumen.partial}</span> parciales
            </span>
            <span className={styles.summaryItem}>
              <span className={styles.summaryCount}>{resumen.absent}</span> ausentes
            </span>
            <span className={styles.summaryItem}>
              <span className={styles.summaryCount}>{resumen.na}</span> no aplican
            </span>
          </div>

          <div className={styles.scroller}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Capacidad</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Pérdida declarada</th>
                  <th scope="col">Plan</th>
                </tr>
              </thead>
              <tbody>
                {grupos.map(([dominio, filas]) => (
                  <Fragment key={dominio}>
                    <tr className={styles.domainRow}>
                      <td colSpan={4}>{dominio}</td>
                    </tr>
                    {filas.map((cap) => (
                      <tr key={cap.key}>
                        <td className={styles.capability}>{cap.key}</td>
                        <td>
                          <StatusCell cap={cap} />
                        </td>
                        <td className={styles.loss}>{cap.loss || "—"}</td>
                        <td className={styles.owner}>
                          {cap.owner_plan ? `#${cap.owner_plan}` : "—"}
                        </td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
