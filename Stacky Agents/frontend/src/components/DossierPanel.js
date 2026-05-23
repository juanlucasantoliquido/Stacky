import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/*
 * DossierPanel — QA UAT dossier viewer
 *
 * Renders the pipeline_result of a QA UAT execution:
 *   - Verdict badge (PASS / FAIL / BLOCKED / MIXED)
 *   - Data Readiness button (Sprint 9): shown when verdict=BLOCKED + category=DATA
 *   - Stage pipeline summary table
 *   - Scenario results table with per-assertion detail
 *   - Failure analysis section (data_drift, regression, etc.)
 *   - Artifact links (trace.zip, video.webm, dossier.json)
 *
 * Displayed below OutputPanel when the active execution has
 * agent_type="qa" and a pipeline_result in metadata.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { QaUat } from "../api/endpoints";
import DataReadinessModal from "./DataReadinessModal";
import SeedPreviewPanel from "./SeedPreviewPanel";
import CatalogDashboard from "./CatalogDashboard";
import OracleDashboard from "./OracleDashboard";
import ConfidenceDashboard from "./ConfidenceDashboard";
import styles from "./DossierPanel.module.css";
// ── Component ─────────────────────────────────────────────────────────────────
export default function DossierPanel({ execution }) {
    const qaRunId = execution.metadata?.qa_uat_execution_id;
    // Sprint 9 — Data Readiness modal state
    const [showDataReadiness, setShowDataReadiness] = useState(false);
    const { data, isLoading, isError } = useQuery({
        queryKey: ["qa-uat-run", qaRunId],
        queryFn: () => QaUat.status(qaRunId),
        enabled: qaRunId != null,
        refetchInterval: (q) => {
            const status = q.state.data?.status;
            return status === "running" || status === "queued" ? 2000 : false;
        },
    });
    if (!qaRunId)
        return null;
    if (isLoading) {
        return (_jsxs("section", { className: styles.panel, children: [_jsx("header", { className: styles.head, children: "QA UAT DOSSIER" }), _jsx("div", { className: styles.loading, children: "cargando pipeline\u2026" })] }));
    }
    if (isError || !data) {
        return (_jsxs("section", { className: styles.panel, children: [_jsx("header", { className: styles.head, children: "QA UAT DOSSIER" }), _jsx("div", { className: styles.error, children: "Error al cargar el resultado del pipeline." })] }));
    }
    const running = data.status === "running" || data.status === "queued";
    const pr = data.pipeline_result;
    // Sprint 9: detect DATA-blocked state to show Data Readiness button
    const isDataBlocked = pr?.verdict === "BLOCKED" &&
        (pr?.category === "DATA" || pr?.failed_stage?.includes("data_readiness") || pr?.failed_stage?.includes("data_resolution"));
    // Sprint 10: detect SQL_SEED_APPROVAL_REQUIRED state to show SeedPreviewPanel
    const isSeedApprovalRequired = pr?.verdict === "BLOCKED" &&
        (pr?.category === "SQL_SEED" ||
            pr?.reason === "SQL_SEED_APPROVAL_REQUIRED" ||
            pr?.failed_stage?.includes("sql_seed"));
    // Sprint 12: detect CATALOG_EMPTY state to show CatalogDashboard
    const hasCatalogIssues = pr?.stages?.catalog_readiness?.empty_count > 0 ||
        pr?.stages?.catalog_readiness?.blocking_empty_count > 0;
    // Sprint 13: detect oracle/weak assertion issues to show OracleDashboard
    const hasOracleIssues = pr?.stages?.oracle_evaluation?.weak_tests > 0 ||
        pr?.stages?.oracle_evaluation?.no_oracle_count > 0 ||
        pr?.stages?.oracle_evaluation?.oracle_publish_blocked === true;
    // Sprint 14: detect low confidence to show ConfidenceDashboard
    const hasConfidenceIssues = pr?.stages?.test_confidence?.low_count > 0 ||
        pr?.stages?.test_confidence?.publish_blocked === true;
    // Extract ticket_id from pipeline result for data requests
    const pipelineTicketId = pr?.ticket_id ?? execution.metadata?.pipeline_ticket_id;
    return (_jsxs(_Fragment, { children: [_jsxs("section", { className: styles.panel, children: [_jsxs("header", { className: styles.head, children: [_jsx("span", { children: "QA UAT DOSSIER" }), _jsxs("div", { className: styles.headRight, children: [running && _jsx("span", { className: styles.running, children: "\u25CF RUNNING" }), pr?.verdict && _jsx(VerdictBadge, { verdict: pr.verdict }), pr?.elapsed_s != null && (_jsxs("span", { className: styles.elapsed, children: [pr.elapsed_s.toFixed(1), "s"] })), isDataBlocked && pipelineTicketId && (_jsx("button", { onClick: () => setShowDataReadiness(true), style: {
                                            marginLeft: "0.5rem",
                                            background: "#b85000",
                                            border: "none",
                                            color: "#fff",
                                            borderRadius: "4px",
                                            padding: "0.2rem 0.6rem",
                                            fontSize: "0.75rem",
                                            fontWeight: 700,
                                            cursor: "pointer",
                                            letterSpacing: "0.03em",
                                        }, title: "Resolver datos faltantes para continuar el pipeline", children: "\uD83D\uDD12 DATOS FALTANTES" }))] })] }), running && !pr && (_jsx("div", { className: styles.runningMsg, children: "Pipeline en ejecuci\u00F3n\u2026" })), pr && (_jsxs("div", { className: styles.body, children: [isDataBlocked && (_jsxs("div", { style: {
                                    background: "rgba(184, 80, 0, 0.15)",
                                    border: "1px solid rgba(184, 80, 0, 0.5)",
                                    borderRadius: "6px",
                                    padding: "0.7rem 1rem",
                                    marginBottom: "0.75rem",
                                    fontSize: "0.82rem",
                                    lineHeight: 1.5,
                                    color: "#ffa07a",
                                }, children: [_jsx("strong", { children: "Pipeline bloqueado por falta de datos" }), pr.reason && _jsxs("span", { children: [" \u2014 ", pr.reason] }), pr.human_action_required && (_jsx("div", { style: { marginTop: "0.3rem", color: "#cccccc" }, children: pr.human_action_required })), _jsx("div", { style: { marginTop: "0.5rem" }, children: _jsx("button", { onClick: () => setShowDataReadiness(true), style: {
                                                background: "#b85000",
                                                border: "none",
                                                color: "#fff",
                                                borderRadius: "4px",
                                                padding: "0.35rem 0.85rem",
                                                fontSize: "0.8rem",
                                                cursor: "pointer",
                                            }, children: "Resolver datos faltantes" }) })] })), pr.stages && _jsx(StageTable, { stages: pr.stages }), isSeedApprovalRequired && pipelineTicketId && (_jsx(SeedPreviewPanel, { runId: String(pipelineTicketId), ticketId: Number(pipelineTicketId) })), hasCatalogIssues && pipelineTicketId && (_jsx(CatalogDashboard, { runId: String(pipelineTicketId), ticketId: Number(pipelineTicketId) })), hasOracleIssues && pipelineTicketId && (_jsx(OracleDashboard, { runId: String(pipelineTicketId), ticketId: Number(pipelineTicketId) })), hasConfidenceIssues && pipelineTicketId && (_jsx(ConfidenceDashboard, { runId: String(pipelineTicketId), ticketId: Number(pipelineTicketId) })), _jsx(EvidenceSection, { metadata: execution.metadata })] })), data.status === "error" && (_jsxs("div", { className: styles.error, children: ["Pipeline fall\u00F3: ", data.error ?? "error desconocido"] }))] }), showDataReadiness && pipelineTicketId && (_jsx(DataReadinessModal, { runId: String(pipelineTicketId), ticketId: Number(pipelineTicketId), onClose: () => setShowDataReadiness(false), onResolved: () => {
                    setShowDataReadiness(false);
                    // Optionally: trigger pipeline resume (out of scope for Sprint 9)
                } }))] }));
}
// ── VerdictBadge ──────────────────────────────────────────────────────────────
function VerdictBadge({ verdict }) {
    return (_jsxs("span", { className: styles.verdict, "data-verdict": verdict, "aria-label": `Verdict: ${verdict}`, children: [verdict === "PASS" && "✓ ", verdict === "FAIL" && "✗ ", verdict === "BLOCKED" && "⊘ ", verdict === "MIXED" && "◑ ", verdict] }));
}
// ── StageTable ────────────────────────────────────────────────────────────────
const STAGE_LABELS = {
    reader: "Ticket reader",
    ui_map: "UI map builder",
    compiler: "Scenario compiler",
    preconditions: "Precondition check",
    generator: "Test generator",
    runner: "Test runner",
    evaluator: "Assertion evaluator",
    failure_analyzer: "Failure analyzer",
    dossier: "Dossier builder",
    publisher: "ADO publisher",
};
const STAGE_ORDER = [
    "reader", "ui_map", "compiler", "preconditions",
    "generator", "runner", "evaluator", "failure_analyzer",
    "dossier", "publisher",
];
function StageTable({ stages }) {
    const [expanded, setExpanded] = useState(false);
    const rows = STAGE_ORDER
        .filter((s) => s in stages)
        .map((s) => ({ key: s, label: STAGE_LABELS[s] ?? s, ...stages[s] }));
    return (_jsxs("div", { className: styles.section, children: [_jsxs("button", { className: styles.sectionToggle, onClick: () => setExpanded((v) => !v), "aria-expanded": expanded, children: [_jsx("span", { className: styles.sectionTitle, children: "PIPELINE STAGES" }), _jsx("span", { className: styles.chevron, children: expanded ? "▲" : "▼" })] }), expanded && (_jsxs("table", { className: styles.table, children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Stage" }), _jsx("th", { children: "Status" }), _jsx("th", { children: "Detail" })] }) }), _jsx("tbody", { children: rows.map((row) => (_jsxs("tr", { children: [_jsx("td", { className: styles.stageLabel, children: row.label }), _jsx("td", { children: _jsx(StageStatus, { ok: row.ok, skipped: row.skipped }) }), _jsx("td", { className: styles.stageDetail, children: _jsx(StageDetail, { stage: row }) })] }, row.key))) })] }))] }));
}
function StageStatus({ ok, skipped }) {
    if (skipped)
        return _jsx("span", { className: styles.skipped, children: "SKIPPED" });
    if (ok)
        return _jsx("span", { className: styles.ok, children: "OK" });
    return _jsx("span", { className: styles.fail, children: "FAIL" });
}
function StageDetail({ stage }) {
    const parts = [];
    if (stage.scenario_count != null)
        parts.push(`${stage.scenario_count} scenarios`);
    if (stage.generated != null)
        parts.push(`${stage.generated} generated`);
    if (stage.pass != null)
        parts.push(`${stage.pass} pass`);
    if (stage.fail != null && stage.fail > 0)
        parts.push(`${stage.fail} fail`);
    if (stage.blocked != null && stage.blocked > 0)
        parts.push(`${stage.blocked} blocked`);
    if (stage.analyzed != null)
        parts.push(`${stage.analyzed} analyzed`);
    if (stage.categories) {
        const cats = Object.entries(stage.categories)
            .map(([k, v]) => `${k}:${v}`)
            .join(", ");
        if (cats)
            parts.push(cats);
    }
    if (stage.verdict)
        parts.push(stage.verdict);
    if (stage.publish_state)
        parts.push(stage.publish_state);
    if (stage.reason)
        parts.push(stage.reason);
    if (stage.error)
        parts.push(`⚠ ${stage.error}`);
    return _jsx("span", { children: parts.join(" · ") || "—" });
}
// ── EvidenceSection ───────────────────────────────────────────────────────────
function EvidenceSection({ metadata }) {
    const evidencePaths = [];
    if (metadata?.dossier_path)
        evidencePaths.push(metadata.dossier_path);
    if (metadata?.evidence_dir)
        evidencePaths.push(metadata.evidence_dir);
    if (evidencePaths.length === 0)
        return null;
    return (_jsxs("div", { className: styles.section, children: [_jsx("div", { className: styles.sectionTitle, children: "EVIDENCIA" }), _jsx("ul", { className: styles.artifactList, children: evidencePaths.map((p) => (_jsx("li", { children: _jsx("span", { className: styles.artifactPath, title: p, children: p.split(/[\\/]/).slice(-2).join("/") }) }, p))) })] }));
}
