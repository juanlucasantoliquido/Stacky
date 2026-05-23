import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * OracleDashboard.tsx — Sprint 13: Oracle Engine + Weak Assertion Detector
 *
 * Renders oracle evaluation results and weak assertion warnings for a QA UAT run.
 *
 * Features:
 *  - Per-scenario oracle verdict (PASS / FAIL / NO_ORACLE / WEAK_ONLY / SKIP)
 *  - P0 blocking indicator when a critical scenario has no oracle
 *  - Weak assertion findings from Playwright spec analysis
 *  - On-demand oracle re-evaluation trigger
 *
 * Used inside DossierPanel when `stages.oracle_evaluation.weak_tests > 0`
 * or `stages.oracle_evaluation.no_oracle_count > 0`.
 *
 * Props:
 *   runId    — pipeline run_id
 *   ticketId — ADO ticket ID
 *
 * Security:
 *   - Read-only display of evidence artifacts.
 *   - On-demand evaluation is safe: no DB writes, no test execution.
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { QaUat } from "../api/endpoints";
import styles from "./OracleDashboard.module.css";
const VERDICT_COLORS = {
    PASS: "#16a34a",
    FAIL: "#dc2626",
    NO_ORACLE: "#9333ea",
    WEAK_ONLY: "#d97706",
    SKIP: "#6b7280",
    ERROR: "#b91c1c",
};
function VerdictBadge({ verdict, small }) {
    const color = VERDICT_COLORS[verdict] ?? "#374151";
    return (_jsx("span", { className: styles.verdictBadge, style: { background: color, fontSize: small ? "11px" : "13px" }, title: verdict, children: verdict }));
}
// ── Strength badge ────────────────────────────────────────────────────────────
const STRENGTH_COLORS = {
    P0: "#16a34a",
    P1: "#2563eb",
    P2: "#d97706",
    NONE: "#6b7280",
};
function StrengthBadge({ strength }) {
    return (_jsx("span", { className: styles.strengthBadge, style: { background: STRENGTH_COLORS[strength] ?? "#374151" }, title: `Oracle strength: ${strength}`, children: strength }));
}
// ── Summary bar ───────────────────────────────────────────────────────────────
function SummaryBar({ result }) {
    return (_jsxs("div", { className: styles.summaryBar, children: [_jsxs("span", { className: styles.summaryItem, children: [_jsx("strong", { children: "Total scenarios:" }), " ", result.total_scenarios] }), _jsxs("span", { className: styles.summaryItem, children: [_jsx("strong", { children: "Evaluated:" }), " ", result.evaluated_scenarios] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#16a34a" }, children: [_jsx("strong", { children: "PASS:" }), " ", result.pass_count] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#dc2626" }, children: [_jsx("strong", { children: "FAIL:" }), " ", result.fail_count] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#9333ea" }, children: [_jsx("strong", { children: "No oracle:" }), " ", result.no_oracle_count] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#d97706" }, children: [_jsx("strong", { children: "Weak only:" }), " ", result.weak_only_count] }), result.publish_blocked && (_jsxs("span", { className: styles.blockingBadge, children: ["\u26D4 P0 BLOCKED (", result.p0_blocked_count, ")"] }))] }));
}
// ── Scenario oracle card ──────────────────────────────────────────────────────
function ScenarioOracleCard({ scenario }) {
    const [expanded, setExpanded] = useState(false);
    return (_jsxs("div", { className: `${styles.scenarioCard} ${scenario.blocking ? styles.blocking : ""}`, children: [_jsxs("div", { className: styles.scenarioHeader, onClick: () => setExpanded((e) => !e), style: { cursor: "pointer" }, children: [_jsx("span", { className: styles.scenarioId, children: scenario.scenario_id }), _jsx(VerdictBadge, { verdict: scenario.oracle_verdict }), scenario.is_p0 && _jsx("span", { className: styles.p0Tag, children: "P0" }), scenario.blocking && _jsx("span", { className: styles.blockingTag, children: "\u26D4 BLOCKING" }), _jsxs("span", { className: styles.oracleCounts, children: [scenario.oracle_count, " oracle", scenario.oracle_count !== 1 ? "s" : "", " · ", _jsxs("span", { style: { color: "#16a34a" }, children: [scenario.pass_count, " pass"] }), " · ", _jsxs("span", { style: { color: "#dc2626" }, children: [scenario.fail_count, " fail"] })] }), _jsx("span", { className: styles.expandIcon, children: expanded ? "▾" : "▸" })] }), expanded && (_jsx("div", { className: styles.oracleChecks, children: scenario.oracle_checks.length === 0 ? (_jsxs("p", { className: styles.noOracle, children: ["No oracle contracts defined for this scenario.", scenario.is_p0 && " This is a P0 scenario — an oracle is required to publish."] })) : (scenario.oracle_checks.map((check, idx) => (_jsxs("div", { className: styles.oracleCheck, children: [_jsx("span", { className: styles.checkId, children: check.oracle_id }), _jsx(VerdictBadge, { verdict: check.verdict, small: true }), _jsx(StrengthBadge, { strength: check.strength }), _jsx("span", { className: styles.checkType, children: check.oracle_type }), _jsx("span", { className: styles.checkDesc, children: check.description }), check.error && (_jsxs("span", { className: styles.checkError, title: check.error, children: ["\u26A0 ", check.error] }))] }, idx)))) }))] }));
}
// ── Weak assertion file card ──────────────────────────────────────────────────
function WeakFileCard({ analysis }) {
    const [expanded, setExpanded] = useState(false);
    return (_jsxs("div", { className: `${styles.weakFileCard} ${analysis.has_weak_tests ? styles.hasWeak : ""}`, children: [_jsxs("div", { className: styles.weakFileHeader, onClick: () => setExpanded((e) => !e), style: { cursor: "pointer" }, children: [_jsx("span", { className: styles.fileName, children: analysis.file_name }), _jsxs("span", { className: styles.weakCounts, children: [_jsxs("span", { style: { color: "#16a34a" }, children: [analysis.strong_tests, " strong"] }), " · ", _jsxs("span", { style: { color: "#d97706" }, children: [analysis.weak_tests, " weak"] }), " · ", _jsxs("span", { style: { color: "#9333ea" }, children: [analysis.trivial_tests, " trivial"] }), " · ", _jsxs("span", { style: { color: "#6b7280" }, children: [analysis.no_assertion_tests, " none"] })] }), _jsx("span", { className: styles.expandIcon, children: expanded ? "▾" : "▸" })] }), expanded && (_jsxs("div", { className: styles.weakTests, children: [analysis.test_results.filter((t) => t.is_weak).map((t, idx) => (_jsxs("div", { className: styles.weakTest, children: [_jsxs("span", { className: styles.weakTestName, children: [t.line_number ? `L${t.line_number}: ` : "", t.test_name] }), _jsxs("span", { className: styles.weakStrength, style: { color: STRENGTH_COLORS[t.assertion_strength] ?? "#374151" }, children: ["[", t.assertion_strength, "]"] }), t.finding && (_jsx("span", { className: styles.weakFinding, title: t.finding, children: t.finding }))] }, idx))), analysis.test_results.filter((t) => t.is_weak).length === 0 && (_jsx("p", { className: styles.allStrong, children: "All tests have strong assertions \u2713" }))] }))] }));
}
export default function OracleDashboard({ runId, ticketId }) {
    const queryClient = useQueryClient();
    // Load oracle evaluation results
    const { data: oracleData, isLoading: oracleLoading } = useQuery({
        queryKey: ["oracle-results", runId, ticketId],
        queryFn: () => QaUat.listOracleResults(runId, ticketId),
        retry: 1,
    });
    // Load weak assertion report
    const { data: weakData, isLoading: weakLoading } = useQuery({
        queryKey: ["weak-assertions", runId, ticketId],
        queryFn: () => QaUat.getWeakAssertions(runId, ticketId),
        retry: 1,
    });
    // On-demand evaluation mutation
    const evaluateMutation = useMutation({
        mutationFn: () => QaUat.evaluateOracles({ run_id: runId, ticket_id: ticketId }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["oracle-results", runId, ticketId] });
            queryClient.invalidateQueries({ queryKey: ["weak-assertions", runId, ticketId] });
        },
    });
    const oracleResult = oracleData?.results?.[0] ?? null;
    const weakReport = weakData?.report ?? null;
    return (_jsxs("div", { className: styles.container, children: [_jsxs("div", { className: styles.header, children: [_jsx("h3", { className: styles.title, children: "Oracle Engine \u2014 Sprint 13" }), _jsx("button", { className: styles.evaluateBtn, onClick: () => evaluateMutation.mutate(), disabled: evaluateMutation.isPending, children: evaluateMutation.isPending ? "Evaluando..." : "⚡ Evaluar oracles" })] }), evaluateMutation.isError && (_jsxs("div", { className: styles.errorBanner, children: ["Error al evaluar: ", String(evaluateMutation.error)] })), _jsxs("section", { className: styles.section, children: [_jsx("h4", { className: styles.sectionTitle, children: "Oracle Contracts" }), oracleLoading && _jsx("p", { className: styles.loading, children: "Cargando resultados oracle\u2026" }), !oracleLoading && !oracleResult && (_jsx("p", { className: styles.empty, children: "No hay oracle_result.json para este run. Hac\u00E9 click en \"Evaluar oracles\" para generar el reporte." })), oracleResult && (_jsxs(_Fragment, { children: [_jsx(SummaryBar, { result: oracleResult }), _jsxs("div", { className: styles.scenarioList, children: [oracleResult.scenario_results.map((sr) => (_jsx(ScenarioOracleCard, { scenario: sr }, sr.scenario_id))), oracleResult.scenario_results.length === 0 && (_jsx("p", { className: styles.empty, children: "Sin escenarios evaluados. El archivo oracle_contracts/ puede estar vac\u00EDo." }))] })] }))] }), _jsxs("section", { className: styles.section, children: [_jsx("h4", { className: styles.sectionTitle, children: "Weak Assertion Detector" }), weakLoading && _jsx("p", { className: styles.loading, children: "Analizando assertions\u2026" }), !weakLoading && !weakReport && (_jsx("p", { className: styles.empty, children: "No hay weak_assertion_report.json para este run. El an\u00E1lisis se genera durante la ejecuci\u00F3n del pipeline." })), weakReport && (_jsxs(_Fragment, { children: [_jsxs("div", { className: styles.summaryBar, children: [_jsxs("span", { className: styles.summaryItem, children: [_jsx("strong", { children: "Archivos:" }), " ", weakReport.files_analyzed] }), _jsxs("span", { className: styles.summaryItem, children: [_jsx("strong", { children: "Tests totales:" }), " ", weakReport.total_tests] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#16a34a" }, children: [_jsx("strong", { children: "Strong:" }), " ", weakReport.strong_tests] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#d97706" }, children: [_jsx("strong", { children: "Weak:" }), " ", weakReport.weak_tests] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#9333ea" }, children: [_jsx("strong", { children: "Trivial:" }), " ", weakReport.trivial_tests] }), _jsxs("span", { className: styles.summaryItem, style: { color: "#6b7280" }, children: [_jsx("strong", { children: "Sin assertions:" }), " ", weakReport.no_assertion_tests] }), weakReport.publish_blocked && (_jsx("span", { className: styles.blockingBadge, children: "\u26D4 PUBLICACI\u00D3N BLOQUEADA" }))] }), _jsxs("div", { className: styles.fileList, children: [weakReport.file_analyses.map((fa) => (_jsx(WeakFileCard, { analysis: fa }, fa.file_name))), weakReport.file_analyses.length === 0 && (_jsx("p", { className: styles.empty, children: "No se analizaron archivos spec." }))] })] }))] })] }));
}
