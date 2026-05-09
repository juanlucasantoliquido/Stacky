/**
 * CatalogDashboard.tsx — Sprint 12: Catalog Readiness Dashboard
 *
 * Renders catalog readiness status for a QA UAT run.
 * Shows per-catalog status (OK / EMPTY / UNVERIFIED / SEED_REQUIRED / PROD_BLOCKED)
 * with row counts, minimum expectations, and seed proposal hints.
 *
 * Used inside DossierPanel when the pipeline detects empty catalogs
 * (`stages.catalog_readiness.empty_count > 0` or `blocking_empty_count > 0`).
 *
 * Also shows a fixture catalog overview via `QaUat.listCatalogFixtures()` so
 * operators can see which catalogs are tracked, even without running a check.
 *
 * Props:
 *   runId      — pipeline run_id
 *   ticketId   — ADO ticket ID
 *   scenarioId — optional filter
 *
 * Security:
 *   - Read-only UI: only displays artifact content from backend.
 *   - No DML triggered from this component — seed proposal requires
 *     human approval via the approve endpoint (Sprint 11).
 */
import React, { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { QaUat } from "../api/endpoints";
import type { CatalogCheckResult, CatalogReadinessResult } from "../api/endpoints";
import styles from "./CatalogDashboard.module.css";

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: CatalogCheckResult["status"] }) {
  const map: Record<string, { cls: string; label: string }> = {
    OK:           { cls: styles.badgeOk,          label: "OK" },
    EMPTY:        { cls: styles.badgeEmpty,        label: "VACÍO" },
    SEED_REQUIRED:{ cls: styles.badgeSeedRequired, label: "SEED REQUERIDO" },
    UNVERIFIED:   { cls: styles.badgeUnverified,   label: "NO VERIFICADO" },
    PROD_BLOCKED: { cls: styles.badgeProdBlocked,  label: "PROD BLOQUEADO" },
  };
  const { cls, label } = map[status] ?? { cls: styles.badgeUnverified, label: status };
  return <span className={cls}>{label}</span>;
}

// ── CatalogCard ────────────────────────────────────────────────────────────────

function CatalogCard({ item }: { item: CatalogCheckResult }) {
  const [open, setOpen] = useState(item.blocking); // expand blocking ones by default

  return (
    <div className={styles.catalogCard}>
      <div className={styles.catalogCardHead} onClick={() => setOpen((v) => !v)}>
        <span>{open ? "▾" : "▸"}</span>
        <span className={styles.catalogName}>{item.catalog_name}</span>
        <span className={styles.dbTable}>{item.db_table}</span>
        <StatusBadge status={item.status} />
        <span className={styles.rowCount}>
          {item.row_count != null
            ? `${item.row_count} / min ${item.min_rows}`
            : "—"}
        </span>
      </div>
      {open && (
        <div className={styles.catalogCardBody}>
          <div>
            <strong>Tabla:</strong> <code>{item.db_table}</code>
          </div>
          <div>
            <strong>Estado:</strong> {item.status}
          </div>
          <div>
            <strong>Bloqueante:</strong> {item.blocking ? "Sí" : "No"}
          </div>
          {item.row_count != null && (
            <div>
              <strong>Filas actuales:</strong> {item.row_count} (mínimo: {item.min_rows})
            </div>
          )}
          {item.error && (
            <div className={styles.errorHint}>
              Error: {item.error}
            </div>
          )}
          {item.seed_proposed && item.seed_script_path && (
            <div className={styles.seedHint}>
              Seed propuesto: {item.seed_script_path.split(/[\\/]/).pop()}
              {" — "}requiere aprobación humana (Sprint 11)
            </div>
          )}
          {item.status === "EMPTY" && !item.seed_proposed && (
            <div className={styles.seedHint}>
              Sin filas suficientes. Agregá seed rows a catalog_fixtures.yml y re-ejecutá.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Summary bar ────────────────────────────────────────────────────────────────

function SummaryBar({ result }: { result: CatalogReadinessResult }) {
  return (
    <div className={styles.summary}>
      <span className={styles.summaryItem}>
        Total: <strong>{result.total}</strong>
      </span>
      {result.ok_count > 0 && (
        <span className={styles.summaryItem}>
          <span className={styles.badgeOk}>{result.ok_count} OK</span>
        </span>
      )}
      {result.empty_count > 0 && (
        <span className={styles.summaryItem}>
          <span className={styles.badgeEmpty}>{result.empty_count} vacíos</span>
        </span>
      )}
      {result.unverified_count > 0 && (
        <span className={styles.summaryItem}>
          <span className={styles.badgeUnverified}>{result.unverified_count} no verificados</span>
        </span>
      )}
      {result.seed_proposed_count > 0 && (
        <span className={styles.summaryItem}>
          <span className={styles.badgeSeedRequired}>{result.seed_proposed_count} seed propuesto</span>
        </span>
      )}
      {result.checked_at && (
        <span className={styles.summaryItem} style={{ marginLeft: "auto", fontSize: "0.68rem" }}>
          {new Date(result.checked_at).toLocaleTimeString()}
        </span>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  runId: string;
  ticketId: number;
  scenarioId?: string;
}

export default function CatalogDashboard({ runId, ticketId, scenarioId }: Props) {
  // Load catalog readiness artifacts from evidence
  const { data, isLoading, isError } = useQuery({
    queryKey: ["catalog-readiness", runId, ticketId, scenarioId],
    queryFn: () => QaUat.listCatalogReadiness(runId, ticketId, scenarioId),
    staleTime: 15_000,
    retry: 1,
  });

  // Load fixture catalog overview
  const { data: fixturesData } = useQuery({
    queryKey: ["catalog-fixtures"],
    queryFn: () => QaUat.listCatalogFixtures(),
    staleTime: 60_000,
    retry: 1,
  });

  // On-demand check mutation
  const checkMutation = useMutation({
    mutationFn: () =>
      QaUat.checkCatalogReadiness({
        run_id: runId,
        ticket_id: ticketId,
        scenario_id: scenarioId,
        required_catalogs: (fixturesData?.fixtures ?? []).map((f) => f.catalog_name),
        dry_run: true,
      }),
  });

  const allResults: CatalogReadinessResult[] = data?.catalogs ?? [];
  const latestResult = checkMutation.data?.result ?? (allResults.length > 0 ? allResults[allResults.length - 1] : null);
  const fixtureTotal = fixturesData?.total ?? 0;

  return (
    <div className={styles.panel}>
      <div className={styles.head}>
        <span>📋 Catálogos</span>
        {latestResult && (
          <span className={latestResult.ok ? styles.badgeOk : styles.badgeEmpty}>
            {latestResult.ok ? "TODOS OK" : `${latestResult.blocking_empty_count} VACÍOS`}
          </span>
        )}
        <div className={styles.headRight}>
          {fixtureTotal > 0 && (
            <span style={{ fontSize: "0.7rem", color: "var(--muted,#888)" }}>
              {fixtureTotal} catálogos definidos
            </span>
          )}
          <button
            className={styles.checkBtn}
            onClick={() => checkMutation.mutate()}
            disabled={checkMutation.isPending || !fixturesData?.fixtures?.length}
            title="Verificar catálogos on-demand (sin conexión DB — UNVERIFIED cuando no hay URL)"
          >
            {checkMutation.isPending ? <span className={styles.spinner} /> : "Verificar"}
          </button>
        </div>
      </div>

      {isLoading && <div className={styles.loading}>Cargando...</div>}
      {isError && !checkMutation.data && (
        <div className={styles.error}>No se pudieron cargar los artefactos de catálogos.</div>
      )}

      {latestResult && (
        <>
          <SummaryBar result={latestResult} />
          <div className={styles.body}>
            {latestResult.catalog_results.length === 0 ? (
              <div className={styles.empty}>No se encontraron catálogos verificados.</div>
            ) : (
              latestResult.catalog_results.map((item) => (
                <CatalogCard key={item.catalog_name} item={item} />
              ))
            )}
          </div>
        </>
      )}

      {!latestResult && !isLoading && !checkMutation.isPending && (
        <div className={styles.body}>
          <div className={styles.empty}>
            No hay resultados de catálogos para este run.
            {fixtureTotal > 0
              ? ` Presioná "Verificar" para chequear los ${fixtureTotal} catálogos definidos.`
              : " No hay catálogos definidos en catalog_fixtures.yml."}
          </div>
          {fixturesData?.fixtures && fixturesData.fixtures.length > 0 && (
            <div style={{ fontSize: "0.72rem", color: "var(--muted,#888)", marginTop: "0.5rem" }}>
              Catálogos definidos: {fixturesData.fixtures.map((f) => f.catalog_name).join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
