import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * ConfidenceDashboard.tsx — Sprint 14: Test Confidence + Data Lineage
 *
 * Shows per-scenario confidence scores and the data lineage audit trail.
 *
 * Features:
 *  - Confidence level (HIGH/MEDIUM/LOW) per scenario with score bar
 *  - Per-factor breakdown showing what contributed/penalized each score
 *  - Publish gate indicator: blocked scenarios highlighted in red
 *  - Data lineage table: field → source → script → cleaned_up
 *  - On-demand re-score and lineage rebuild buttons
 *
 * Displayed in DossierPanel when:
 *  - `stages.test_confidence.publish_blocked === true`
 *  - OR `stages.test_confidence.low_count > 0`
 *
 * Props:
 *   runId    — pipeline run_id
 *   ticketId — ADO ticket ID
 *
 * Security:
 *   - Read-only display — no DB or seed operations triggered.
 *   - Score and lineage re-builds are read-only operations.
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { QaUat } from "../api/endpoints";
import styles from "./ConfidenceDashboard.module.css";
// ── Level colors ──────────────────────────────────────────────────────────────
const LEVEL_COLORS = {
    HIGH: "#16a34a",
    MEDIUM: "#d97706",
    LOW: "#dc2626",
};
// ── Score bar ─────────────────────────────────────────────────────────────────
function ScoreBar({ score, level }) {
    const color = LEVEL_COLORS[level] ?? "#6b7280";
    return (_jsxs("div", { className: styles.scoreBarWrap, title: `Score: ${score}/100`, children: [_jsx("div", { className: styles.scoreBarFill, style: { width: `${Math.max(0, Math.min(100, score))}%`, background: color } }), _jsx("span", { className: styles.scoreBarLabel, children: score })] }));
}
// ── Level badge ───────────────────────────────────────────────────────────────
function LevelBadge({ level }) {
    return (_jsx("span", { className: styles.levelBadge, style: { background: LEVEL_COLORS[level] ?? "#374151" }, children: level }));
}
// ── Source badge ──────────────────────────────────────────────────────────────
const SOURCE_COLORS = {
    SEEDED: "#2563eb",
    USER_SUPPLIED: "#7c3aed",
    FIXTURE: "#0891b2",
    DISCOVERED: "#059669",
    ENVIRONMENT: "#6b7280",
    UNKNOWN: "#374151",
};
function SourceBadge({ source }) {
    return (_jsx("span", { className: styles.sourceBadge, style: { background: SOURCE_COLORS[source] ?? "#374151" }, children: source }));
}
// ── Scenario confidence card ──────────────────────────────────────────────────
function ScenarioConfidenceCard({ cs }) {
    const [expanded, setExpanded] = useState(false);
    const positiveFactors = cs.factors.filter((f) => f.delta > 0);
    const negativeFactors = cs.factors.filter((f) => f.delta < 0);
    return (_jsxs("div", { className: `${styles.scenarioCard} ${cs.publish_blocked ? styles.blocked : ""}`, children: [_jsxs("div", { className: styles.scenarioHeader, onClick: () => setExpanded((e) => !e), style: { cursor: "pointer" }, children: [_jsx("span", { className: styles.scenarioId, children: cs.scenario_id }), _jsx(LevelBadge, { level: cs.level }), cs.is_p0 && _jsx("span", { className: styles.p0Tag, children: "P0" }), cs.publish_blocked && _jsx("span", { className: styles.blockTag, children: "\u26D4 BLOQUEADO" }), _jsx(ScoreBar, { score: cs.score, level: cs.level }), _jsx("span", { className: styles.expandIcon, children: expanded ? "▾" : "▸" })] }), expanded && (_jsxs("div", { className: styles.factorsList, children: [positiveFactors.length > 0 && (_jsxs("div", { className: styles.factorGroup, children: [_jsx("span", { className: styles.factorGroupLabel, style: { color: "#4ade80" }, children: "\u2713 Positivos" }), positiveFactors.map((f, i) => (_jsxs("div", { className: styles.factorRow, children: [_jsxs("span", { className: styles.factorDelta, style: { color: "#4ade80" }, children: ["+", f.delta] }), _jsx("span", { className: styles.factorName, children: f.name }), _jsx("span", { className: styles.factorReason, children: f.reason })] }, i)))] })), negativeFactors.length > 0 && (_jsxs("div", { className: styles.factorGroup, children: [_jsx("span", { className: styles.factorGroupLabel, style: { color: "#fca5a5" }, children: "\u2717 Penalizaciones" }), negativeFactors.map((f, i) => (_jsxs("div", { className: styles.factorRow, children: [_jsx("span", { className: styles.factorDelta, style: { color: "#fca5a5" }, children: f.delta }), _jsx("span", { className: styles.factorName, children: f.name }), _jsx("span", { className: styles.factorReason, children: f.reason })] }, i)))] })), cs.factors.length === 0 && (_jsx("p", { className: styles.noFactors, children: "Sin factores registrados." }))] }))] }));
}
// ── Lineage table ─────────────────────────────────────────────────────────────
function LineageTable({ entries }) {
    if (entries.length === 0) {
        return _jsx("p", { className: styles.empty, children: "Sin entradas de lineage." });
    }
    return (_jsxs("table", { className: styles.lineageTable, children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Campo" }), _jsx("th", { children: "Valor" }), _jsx("th", { children: "Origen" }), _jsx("th", { children: "Escenario" }), _jsx("th", { children: "Script" }), _jsx("th", { children: "Limpiado" }), _jsx("th", { children: "Nota" })] }) }), _jsx("tbody", { children: entries.map((e, i) => (_jsxs("tr", { className: e.cleaned_up ? styles.cleanedRow : "", children: [_jsx("td", { className: styles.fieldCell, children: e.field }), _jsx("td", { className: styles.valueCell, children: e.value ?? _jsx("em", { className: styles.redacted, children: "[redactado]" }) }), _jsx("td", { children: _jsx(SourceBadge, { source: e.source }) }), _jsx("td", { className: styles.scenarioCell, children: e.scenario_id }), _jsx("td", { className: styles.scriptCell, children: e.seed_script ?? "—" }), _jsx("td", { className: styles.cleanedCell, children: e.cleaned_up
                                ? _jsx("span", { className: styles.cleanedYes, children: "\u2713" })
                                : _jsx("span", { className: styles.cleanedNo, children: "\u2717" }) }), _jsx("td", { className: styles.noteCell, children: e.origin_note ?? "—" })] }, i))) })] }));
}
// ── Summary bar ───────────────────────────────────────────────────────────────
function ConfidenceSummaryBar({ report }) {
    return (_jsxs("div", { className: styles.summaryBar, children: [_jsxs("span", { className: styles.summaryItem, children: [_jsx("strong", { children: "Escenarios:" }), " ", report.total_scenarios] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#16a34a" }, children: [_jsx("strong", { children: "HIGH:" }), " ", report.high_count] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#d97706" }, children: [_jsx("strong", { children: "MEDIUM:" }), " ", report.medium_count] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#dc2626" }, children: [_jsx("strong", { children: "LOW:" }), " ", report.low_count] }), _jsxs("span", { className: styles.summaryItem, children: [_jsx("strong", { children: "Gate m\u00EDnimo:" }), " ", report.min_confidence] }), report.publish_blocked && (_jsxs("span", { className: styles.blockingBadge, children: ["\u26D4 PUBLICACI\u00D3N BLOQUEADA (", report.blocked_count, " escenarios)"] }))] }));
}
export default function ConfidenceDashboard({ runId, ticketId }) {
    const queryClient = useQueryClient();
    const [activeTab, setActiveTab] = useState("confidence");
    // Load confidence report
    const { data: confData, isLoading: confLoading } = useQuery({
        queryKey: ["confidence-report", runId, ticketId],
        queryFn: () => QaUat.getConfidenceReport(runId, ticketId),
        retry: 1,
    });
    // Load data lineage
    const { data: lineageData, isLoading: lineageLoading } = useQuery({
        queryKey: ["data-lineage", runId, ticketId],
        queryFn: () => QaUat.getDataLineage(runId, ticketId),
        retry: 1,
    });
    // Re-score mutation
    const scoreMutation = useMutation({
        mutationFn: () => QaUat.scoreConfidence({ run_id: runId, ticket_id: ticketId }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["confidence-report", runId, ticketId] });
        },
    });
    // Build lineage mutation
    const lineageMutation = useMutation({
        mutationFn: () => QaUat.buildDataLineage({ run_id: runId, ticket_id: ticketId }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["data-lineage", runId, ticketId] });
        },
    });
    const report = confData?.report ?? null;
    const lineage = lineageData?.lineage ?? null;
    return (_jsxs("div", { className: styles.container, children: [_jsxs("div", { className: styles.header, children: [_jsx("h3", { className: styles.title, children: "Test Confidence \u2014 Sprint 14" }), _jsxs("div", { className: styles.headerActions, children: [_jsx("button", { className: styles.actionBtn, onClick: () => scoreMutation.mutate(), disabled: scoreMutation.isPending, children: scoreMutation.isPending ? "Calculando..." : "⚡ Re-score" }), _jsx("button", { className: styles.actionBtn, onClick: () => lineageMutation.mutate(), disabled: lineageMutation.isPending, children: lineageMutation.isPending ? "Construyendo..." : "🔗 Build lineage" })] })] }), _jsxs("div", { className: styles.tabs, children: [_jsx("button", { className: `${styles.tab} ${activeTab === "confidence" ? styles.tabActive : ""}`, onClick: () => setActiveTab("confidence"), children: "Confidence" }), _jsxs("button", { className: `${styles.tab} ${activeTab === "lineage" ? styles.tabActive : ""}`, onClick: () => setActiveTab("lineage"), children: ["Data Lineage", lineage && ` (${lineage.total_entries})`] })] }), activeTab === "confidence" && (_jsxs("div", { className: styles.tabContent, children: [confLoading && _jsx("p", { className: styles.loading, children: "Cargando reporte\u2026" }), !confLoading && !report && (_jsx("p", { className: styles.empty, children: "Sin confidence_report.json. Hac\u00E9 click en \"Re-score\" para generarlo." })), report && (_jsxs(_Fragment, { children: [_jsx(ConfidenceSummaryBar, { report: report }), _jsxs("div", { className: styles.scenarioList, children: [report.scenario_scores.map((cs) => (_jsx(ScenarioConfidenceCard, { cs: cs }, cs.scenario_id))), report.scenario_scores.length === 0 && (_jsx("p", { className: styles.empty, children: "Sin escenarios puntuados." }))] })] }))] })), activeTab === "lineage" && (_jsxs("div", { className: styles.tabContent, children: [lineageLoading && _jsx("p", { className: styles.loading, children: "Cargando lineage\u2026" }), !lineageLoading && !lineage && (_jsx("p", { className: styles.empty, children: "Sin data_lineage.json. Hac\u00E9 click en \"Build lineage\" para generarlo." })), lineage && (_jsxs(_Fragment, { children: [_jsxs("div", { className: styles.summaryBar, children: [_jsxs("span", { className: styles.summaryItem, children: [_jsx("strong", { children: "Total entradas:" }), " ", lineage.total_entries] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#2563eb" }, children: [_jsx("strong", { children: "Seeded:" }), " ", lineage.seeded_count] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#7c3aed" }, children: [_jsx("strong", { children: "User supplied:" }), " ", lineage.user_supplied_count] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#0891b2" }, children: [_jsx("strong", { children: "Fixture:" }), " ", lineage.fixture_count] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#059669" }, children: [_jsx("strong", { children: "Discovered:" }), " ", lineage.discovered_count] })] }), _jsx("div", { className: styles.lineageWrap, children: _jsx(LineageTable, { entries: lineage.entries }) })] }))] }))] }));
}
