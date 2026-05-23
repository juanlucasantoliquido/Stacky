import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
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
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { QaUat } from "../api/endpoints";
import styles from "./CatalogDashboard.module.css";
// ── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
    const map = {
        OK: { cls: styles.badgeOk, label: "OK" },
        EMPTY: { cls: styles.badgeEmpty, label: "VACÍO" },
        SEED_REQUIRED: { cls: styles.badgeSeedRequired, label: "SEED REQUERIDO" },
        UNVERIFIED: { cls: styles.badgeUnverified, label: "NO VERIFICADO" },
        PROD_BLOCKED: { cls: styles.badgeProdBlocked, label: "PROD BLOQUEADO" },
    };
    const { cls, label } = map[status] ?? { cls: styles.badgeUnverified, label: status };
    return _jsx("span", { className: cls, children: label });
}
// ── CatalogCard ────────────────────────────────────────────────────────────────
function CatalogCard({ item }) {
    const [open, setOpen] = useState(item.blocking); // expand blocking ones by default
    return (_jsxs("div", { className: styles.catalogCard, children: [_jsxs("div", { className: styles.catalogCardHead, onClick: () => setOpen((v) => !v), children: [_jsx("span", { children: open ? "▾" : "▸" }), _jsx("span", { className: styles.catalogName, children: item.catalog_name }), _jsx("span", { className: styles.dbTable, children: item.db_table }), _jsx(StatusBadge, { status: item.status }), _jsx("span", { className: styles.rowCount, children: item.row_count != null
                            ? `${item.row_count} / min ${item.min_rows}`
                            : "—" })] }), open && (_jsxs("div", { className: styles.catalogCardBody, children: [_jsxs("div", { children: [_jsx("strong", { children: "Tabla:" }), " ", _jsx("code", { children: item.db_table })] }), _jsxs("div", { children: [_jsx("strong", { children: "Estado:" }), " ", item.status] }), _jsxs("div", { children: [_jsx("strong", { children: "Bloqueante:" }), " ", item.blocking ? "Sí" : "No"] }), item.row_count != null && (_jsxs("div", { children: [_jsx("strong", { children: "Filas actuales:" }), " ", item.row_count, " (m\u00EDnimo: ", item.min_rows, ")"] })), item.error && (_jsxs("div", { className: styles.errorHint, children: ["Error: ", item.error] })), item.seed_proposed && item.seed_script_path && (_jsxs("div", { className: styles.seedHint, children: ["Seed propuesto: ", item.seed_script_path.split(/[\\/]/).pop(), " — ", "requiere aprobaci\u00F3n humana (Sprint 11)"] })), item.status === "EMPTY" && !item.seed_proposed && (_jsx("div", { className: styles.seedHint, children: "Sin filas suficientes. Agreg\u00E1 seed rows a catalog_fixtures.yml y re-ejecut\u00E1." }))] }))] }));
}
// ── Summary bar ────────────────────────────────────────────────────────────────
function SummaryBar({ result }) {
    return (_jsxs("div", { className: styles.summary, children: [_jsxs("span", { className: styles.summaryItem, children: ["Total: ", _jsx("strong", { children: result.total })] }), result.ok_count > 0 && (_jsx("span", { className: styles.summaryItem, children: _jsxs("span", { className: styles.badgeOk, children: [result.ok_count, " OK"] }) })), result.empty_count > 0 && (_jsx("span", { className: styles.summaryItem, children: _jsxs("span", { className: styles.badgeEmpty, children: [result.empty_count, " vac\u00EDos"] }) })), result.unverified_count > 0 && (_jsx("span", { className: styles.summaryItem, children: _jsxs("span", { className: styles.badgeUnverified, children: [result.unverified_count, " no verificados"] }) })), result.seed_proposed_count > 0 && (_jsx("span", { className: styles.summaryItem, children: _jsxs("span", { className: styles.badgeSeedRequired, children: [result.seed_proposed_count, " seed propuesto"] }) })), result.checked_at && (_jsx("span", { className: styles.summaryItem, style: { marginLeft: "auto", fontSize: "0.68rem" }, children: new Date(result.checked_at).toLocaleTimeString() }))] }));
}
export default function CatalogDashboard({ runId, ticketId, scenarioId }) {
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
        mutationFn: () => QaUat.checkCatalogReadiness({
            run_id: runId,
            ticket_id: ticketId,
            scenario_id: scenarioId,
            required_catalogs: (fixturesData?.fixtures ?? []).map((f) => f.catalog_name),
            dry_run: true,
        }),
    });
    const allResults = data?.catalogs ?? [];
    const latestResult = checkMutation.data?.result ?? (allResults.length > 0 ? allResults[allResults.length - 1] : null);
    const fixtureTotal = fixturesData?.total ?? 0;
    return (_jsxs("div", { className: styles.panel, children: [_jsxs("div", { className: styles.head, children: [_jsx("span", { children: "\uD83D\uDCCB Cat\u00E1logos" }), latestResult && (_jsx("span", { className: latestResult.ok ? styles.badgeOk : styles.badgeEmpty, children: latestResult.ok ? "TODOS OK" : `${latestResult.blocking_empty_count} VACÍOS` })), _jsxs("div", { className: styles.headRight, children: [fixtureTotal > 0 && (_jsxs("span", { style: { fontSize: "0.7rem", color: "var(--muted,#888)" }, children: [fixtureTotal, " cat\u00E1logos definidos"] })), _jsx("button", { className: styles.checkBtn, onClick: () => checkMutation.mutate(), disabled: checkMutation.isPending || !fixturesData?.fixtures?.length, title: "Verificar cat\u00E1logos on-demand (sin conexi\u00F3n DB \u2014 UNVERIFIED cuando no hay URL)", children: checkMutation.isPending ? _jsx("span", { className: styles.spinner }) : "Verificar" })] })] }), isLoading && _jsx("div", { className: styles.loading, children: "Cargando..." }), isError && !checkMutation.data && (_jsx("div", { className: styles.error, children: "No se pudieron cargar los artefactos de cat\u00E1logos." })), latestResult && (_jsxs(_Fragment, { children: [_jsx(SummaryBar, { result: latestResult }), _jsx("div", { className: styles.body, children: latestResult.catalog_results.length === 0 ? (_jsx("div", { className: styles.empty, children: "No se encontraron cat\u00E1logos verificados." })) : (latestResult.catalog_results.map((item) => (_jsx(CatalogCard, { item: item }, item.catalog_name)))) })] })), !latestResult && !isLoading && !checkMutation.isPending && (_jsxs("div", { className: styles.body, children: [_jsxs("div", { className: styles.empty, children: ["No hay resultados de cat\u00E1logos para este run.", fixtureTotal > 0
                                ? ` Presioná "Verificar" para chequear los ${fixtureTotal} catálogos definidos.`
                                : " No hay catálogos definidos en catalog_fixtures.yml."] }), fixturesData?.fixtures && fixturesData.fixtures.length > 0 && (_jsxs("div", { style: { fontSize: "0.72rem", color: "var(--muted,#888)", marginTop: "0.5rem" }, children: ["Cat\u00E1logos definidos: ", fixturesData.fixtures.map((f) => f.catalog_name).join(", ")] }))] }))] }));
}
