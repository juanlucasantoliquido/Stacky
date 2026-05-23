import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import React, { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PmApi, } from "../api/pm";
import styles from "./PMCommandCenter.module.css";
function fmtDate(iso) {
    if (!iso)
        return "—";
    try {
        return new Date(iso).toLocaleDateString("es-AR", {
            day: "2-digit",
            month: "short",
            year: "numeric",
        });
    }
    catch {
        return iso;
    }
}
function fmtDateTime(iso) {
    if (!iso)
        return "—";
    try {
        return new Date(iso).toLocaleString("es-AR", { hour12: false });
    }
    catch {
        return iso;
    }
}
function healthClass(kpis) {
    if (!kpis || kpis.total_items === 0)
        return styles.healthGray;
    const completion = kpis.completion_rate_pct;
    if (kpis.blocked_items > 0 && (kpis.days_remaining ?? 99) <= 2)
        return styles.healthRed;
    if (completion >= 75)
        return styles.healthGreen;
    if (completion >= 50)
        return styles.healthYellow;
    return styles.healthRed;
}
function healthLabel(kpis) {
    if (!kpis || kpis.total_items === 0)
        return "Sin datos";
    const cls = healthClass(kpis);
    if (cls === styles.healthGreen)
        return "Saludable";
    if (cls === styles.healthYellow)
        return "Atención";
    if (cls === styles.healthRed)
        return "En riesgo";
    return "Sin datos";
}
function KpiCard({ label, value, sub }) {
    return (_jsxs("div", { className: styles.kpiCard, children: [_jsx("div", { className: styles.kpiLabel, children: label }), _jsx("div", { className: styles.kpiValue, children: value }), sub && _jsx("div", { className: styles.kpiSub, children: sub })] }));
}
function SprintHealthCard({ snapshot, capturedAt }) {
    const kpis = snapshot?.snapshot?.kpis ?? null;
    const iteration = snapshot?.snapshot?.iteration ?? null;
    return (_jsxs("div", { className: styles.sprintCard, children: [_jsxs("div", { className: styles.sprintTop, children: [_jsx("h2", { className: styles.sprintName, children: snapshot?.sprint_name ?? "Sin sprint sincronizado" }), _jsxs("span", { className: styles.sprintMeta, children: [fmtDate(iteration?.start_date ?? snapshot?.start_date ?? null), " → ", fmtDate(iteration?.end_date ?? snapshot?.end_date ?? null)] }), _jsx("span", { className: `${styles.healthPill} ${healthClass(kpis)}`, children: healthLabel(kpis) }), capturedAt && (_jsxs("span", { className: styles.sprintMeta, children: ["\u00DAltimo sync: ", fmtDateTime(capturedAt)] }))] }), _jsxs("div", { className: styles.kpiGrid, children: [_jsx(KpiCard, { label: "Completion", value: kpis ? `${kpis.completion_rate_pct.toFixed(0)}%` : "—", sub: kpis && kpis.committed_story_points > 0
                            ? `${kpis.completed_story_points}/${kpis.committed_story_points} pts`
                            : kpis
                                ? `${kpis.done_items}/${kpis.total_items} items`
                                : undefined }), _jsx(KpiCard, { label: "Total items", value: kpis?.total_items ?? "—", sub: kpis
                            ? `${kpis.active_items} activos · ${kpis.blocked_items} bloqueados`
                            : undefined }), _jsx(KpiCard, { label: "Bugs", value: kpis ? `${kpis.bug_count}` : "—", sub: kpis ? `${kpis.bug_rate_pct.toFixed(1)}% del sprint` : undefined }), _jsx(KpiCard, { label: "D\u00EDas restantes", value: kpis?.days_remaining ?? "—" }), _jsx(KpiCard, { label: "Aging promedio", value: kpis?.avg_aging_days != null ? `${kpis.avg_aging_days.toFixed(1)}d` : "—" }), _jsx(KpiCard, { label: "Cycle time", value: kpis?.avg_cycle_time_days != null ? `${kpis.avg_cycle_time_days.toFixed(1)}d` : "—", sub: "promedio del sprint" }), _jsx(KpiCard, { label: "Sin estimaci\u00F3n", value: kpis?.items_without_estimation ?? "—" }), _jsx(KpiCard, { label: "Sin owner", value: kpis?.items_without_owner ?? "—" })] }), kpis && kpis.data_quality_warnings.length > 0 && (_jsx("ul", { className: styles.dqList, children: kpis.data_quality_warnings.map((w, i) => (_jsxs("li", { className: styles.dqItem, children: [_jsx("strong", { children: w.warning_type }), " \u2014 ", w.impact, " ", "(", w.count, ", ", w.percentage, "%)"] }, `${w.warning_type}-${i}`))) }))] }));
}
function RiskFeed({ risks, onAcknowledge, ackInFlight }) {
    if (risks.length === 0) {
        return _jsx("div", { className: styles.empty, children: "Sin riesgos detectados para los filtros actuales." });
    }
    return (_jsx("div", { className: styles.riskList, children: risks.map((r) => {
            const sevClass = styles[`severity${r.severity}`] ?? "";
            return (_jsxs("div", { className: `${styles.riskItem} ${sevClass} ${r.acknowledged ? styles.ackd : ""}`, children: [_jsxs("div", { className: styles.riskHeader, children: [_jsx("span", { className: `${styles.severityBadge} ${sevClass}`, children: r.severity }), _jsx("span", { className: styles.riskCategory, children: r.category }), r.rule && _jsx("span", { className: styles.riskRule, children: r.rule }), r.acknowledged ? (_jsxs("span", { className: styles.ackedMark, children: ["\u2713 acknowledged por ", r.acknowledged_by ?? "?", " (", fmtDateTime(r.acknowledged_at), ")"] })) : (_jsx("button", { className: styles.btnAck, onClick: () => onAcknowledge(r.risk_id), disabled: ackInFlight === r.risk_id, children: ackInFlight === r.risk_id ? "..." : "Acknowledge" }))] }), _jsx("div", { className: styles.riskDescription, children: r.description ?? "(sin descripción)" }), _jsxs("div", { className: styles.riskMeta, children: [_jsxs("span", { children: ["ID: ", r.risk_id] }), r.affected_items.length > 0 && (_jsxs("span", { className: styles.riskItems, children: ["Items: ", r.affected_items.slice(0, 8).join(", "), r.affected_items.length > 8 ? ` (+${r.affected_items.length - 8} más)` : ""] })), _jsxs("span", { children: ["Detectado: ", fmtDateTime(r.detected_at)] })] })] }, r.risk_id));
        }) }));
}
// ── AI Usage Panel ────────────────────────────────────────────────────────────
function fmtNum(n) {
    if (n >= 1_000_000)
        return `${(n / 1_000_000).toFixed(2)}M`;
    if (n >= 1_000)
        return `${(n / 1_000).toFixed(1)}k`;
    return n.toString();
}
function fmtCost(usd) {
    if (usd === 0)
        return "$0";
    if (usd < 0.01)
        return `$${usd.toFixed(4)}`;
    if (usd < 1)
        return `$${usd.toFixed(3)}`;
    return `$${usd.toFixed(2)}`;
}
function AIUsagePanel({ report, windowHours, onWindowChange, loading }) {
    const totals = report?.totals;
    const byModel = report?.by_model ?? {};
    const byAgent = report?.by_agent ?? {};
    const recent = report?.recent_calls ?? [];
    const breakdownRow = (key, data) => (_jsxs("tr", { children: [_jsx("td", { className: styles.mono, children: key }), _jsx("td", { className: styles.numeric, children: data.calls }), _jsx("td", { className: styles.numeric, children: fmtNum(data.tokens_in) }), _jsx("td", { className: styles.numeric, children: fmtNum(data.tokens_out) }), _jsx("td", { className: styles.numeric, children: fmtCost(data.cost_usd) }), _jsx("td", { className: styles.numeric, children: data.calls > 0 ? `${((data.success / data.calls) * 100).toFixed(0)}%` : "—" })] }, key));
    return (_jsxs("section", { className: styles.aiPanel, children: [_jsxs("div", { className: styles.aiHeader, children: [_jsx("h3", { className: styles.aiTitle, children: "\uD83E\uDD16 AI Usage Tracking" }), _jsx("span", { className: styles.advisoryBadge, children: "advisory_only" }), _jsxs("span", { className: styles.aiWindow, children: ["Ventana: \u00FAltimas ", windowHours, "h", report?.window_start && ` · desde ${new Date(report.window_start).toLocaleString("es-AR")}`] }), _jsxs("select", { className: styles.aiSelector, value: windowHours, onChange: (e) => onWindowChange(parseInt(e.target.value, 10)), children: [_jsx("option", { value: 1, children: "1h" }), _jsx("option", { value: 24, children: "24h" }), _jsx("option", { value: 72, children: "3d" }), _jsx("option", { value: 168, children: "7d" })] })] }), _jsxs("div", { className: styles.aiTotalsGrid, children: [_jsxs("div", { className: styles.aiKpi, children: [_jsx("div", { className: styles.aiKpiLabel, children: "Costo USD" }), _jsx("div", { className: styles.aiKpiValue, children: loading ? "..." : fmtCost(totals?.cost_usd ?? 0) }), _jsxs("div", { className: styles.aiKpiSub, children: [totals?.calls ?? 0, " llamadas"] })] }), _jsxs("div", { className: styles.aiKpi, children: [_jsx("div", { className: styles.aiKpiLabel, children: "Tokens in" }), _jsx("div", { className: styles.aiKpiValue, children: fmtNum(totals?.tokens_in ?? 0) })] }), _jsxs("div", { className: styles.aiKpi, children: [_jsx("div", { className: styles.aiKpiLabel, children: "Tokens out" }), _jsx("div", { className: styles.aiKpiValue, children: fmtNum(totals?.tokens_out ?? 0) })] }), _jsxs("div", { className: styles.aiKpi, children: [_jsx("div", { className: styles.aiKpiLabel, children: "Total tokens" }), _jsx("div", { className: styles.aiKpiValue, children: fmtNum(totals?.tokens_total ?? 0) })] }), _jsxs("div", { className: styles.aiKpi, children: [_jsx("div", { className: styles.aiKpiLabel, children: "Success rate" }), _jsx("div", { className: styles.aiKpiValue, children: totals && totals.calls > 0 ? `${totals.success_rate_pct.toFixed(0)}%` : "—" }), _jsxs("div", { className: styles.aiKpiSub, children: [totals?.success ?? 0, "/", totals?.calls ?? 0] })] }), _jsxs("div", { className: styles.aiKpi, children: [_jsx("div", { className: styles.aiKpiLabel, children: "Latencia avg" }), _jsx("div", { className: styles.aiKpiValue, children: totals && totals.calls > 0 ? `${(totals.latency_ms_avg / 1000).toFixed(1)}s` : "—" })] })] }), Object.keys(byModel).length > 0 && (_jsxs("div", { className: styles.aiBreakdownSection, children: [_jsx("h4", { className: styles.aiBreakdownTitle, children: "Por modelo" }), _jsxs("table", { className: styles.aiBreakdownTable, children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Modelo" }), _jsx("th", { style: { textAlign: "right" }, children: "Calls" }), _jsx("th", { style: { textAlign: "right" }, children: "Tokens in" }), _jsx("th", { style: { textAlign: "right" }, children: "Tokens out" }), _jsx("th", { style: { textAlign: "right" }, children: "Costo" }), _jsx("th", { style: { textAlign: "right" }, children: "Success" })] }) }), _jsx("tbody", { children: Object.entries(byModel).map(([k, v]) => breakdownRow(k, v)) })] })] })), Object.keys(byAgent).length > 0 && (_jsxs("div", { className: styles.aiBreakdownSection, children: [_jsx("h4", { className: styles.aiBreakdownTitle, children: "Por agente" }), _jsxs("table", { className: styles.aiBreakdownTable, children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Agente" }), _jsx("th", { style: { textAlign: "right" }, children: "Calls" }), _jsx("th", { style: { textAlign: "right" }, children: "Tokens in" }), _jsx("th", { style: { textAlign: "right" }, children: "Tokens out" }), _jsx("th", { style: { textAlign: "right" }, children: "Costo" }), _jsx("th", { style: { textAlign: "right" }, children: "Success" })] }) }), _jsx("tbody", { children: Object.entries(byAgent).map(([k, v]) => breakdownRow(k, v)) })] })] })), recent.length > 0 && (_jsxs("div", { className: styles.aiBreakdownSection, children: [_jsxs("h4", { className: styles.aiBreakdownTitle, children: ["\u00DAltimas ", recent.length, " llamadas"] }), _jsx("div", { className: styles.aiRecent, children: recent.map((r) => (_jsxs("div", { className: `${styles.aiRecentRow} ${!r.success ? styles.failed : ""}`, children: [_jsx("span", { className: styles.aiTimestamp, children: new Date(r.timestamp).toLocaleTimeString("es-AR", { hour12: false }) }), _jsx("span", { className: styles.aiAgent, children: r.agent_kind }), _jsx("span", { className: styles.aiModel, children: r.model }), _jsxs("span", { className: styles.aiTokens, children: [fmtNum(r.tokens_in), "\u2193 ", fmtNum(r.tokens_out), "\u2191"] }), _jsx("span", { className: styles.aiCost, children: fmtCost(r.cost_usd) }), !r.success && _jsx("span", { className: styles.aiErr, children: r.error ?? "error" })] }, r.id))) })] })), !loading && (totals?.calls ?? 0) === 0 && (_jsx("div", { className: styles.empty, children: "A\u00FAn no hay llamadas IA registradas en esta ventana. Cuando se ejecuten an\u00E1lisis de sentiment o recommendations, aparecer\u00E1n ac\u00E1 con su consumo de tokens y costo USD para que puedas ajustar el presupuesto." }))] }));
}
function gateBadge(report) {
    if (!report)
        return { label: "no corrida", cls: styles.gateUnknown };
    return report.gate_passed
        ? { label: "passed", cls: styles.gatePass }
        : { label: "failed", cls: styles.gateFail };
}
function fmtPricing(m) {
    if (!m.pricing_per_1m_usd)
        return "";
    const p = m.pricing_per_1m_usd;
    if (p.input === 0 && p.output === 0)
        return " (mock)";
    return ` ($${p.input.toFixed(2)}/${p.output.toFixed(2)} per 1M)`;
}
function AIControlPanel({ sentimentReport, recReport, onRunEvals, onGenerateRecs, runningEvals, generatingRecs, lastRecRun, modelsReport, modelsLoading, selectedModel, onModelChange, }) {
    const sentimentBadge = gateBadge(sentimentReport);
    const recBadge = gateBadge(recReport);
    const recGateFailed = recReport ? !recReport.gate_passed : false;
    const models = modelsReport?.models ?? [];
    const backendLabel = modelsReport?.backend ?? "?";
    const modelsError = modelsReport?.error ?? null;
    return (_jsxs("section", { className: styles.ctrlPanel, children: [_jsxs("div", { className: styles.ctrlHeader, children: [_jsx("h3", { className: styles.ctrlTitle, children: "\uD83E\uDDEA AI Components \u00B7 Evals & Run" }), _jsx("span", { className: styles.advisoryBadge, children: "advisory_only" }), _jsx("span", { className: styles.ctrlSubtitle, children: "Los componentes IA solo se habilitan si pasan sus eval fixtures" })] }), _jsxs("div", { className: styles.modelSelectorBar, children: [_jsx("span", { className: styles.filterLabel, children: "Modelo:" }), _jsxs("select", { className: styles.modelSelect, value: selectedModel, onChange: (e) => onModelChange(e.target.value), disabled: modelsLoading || models.length === 0, title: "Modelo usado para evals, sentiment y recommendations", children: [models.length === 0 && _jsx("option", { value: "", children: "Cargando modelos..." }), models.map((m) => (_jsxs("option", { value: m.id, children: [m.name, m.is_premium ? " ⭐" : "", m.preview ? " (preview)" : "", fmtPricing(m)] }, m.id)))] }), _jsxs("span", { className: styles.modelBackend, children: ["backend: ", backendLabel] }), modelsError && (_jsx("span", { className: styles.modelWarning, title: modelsError, children: "\u26A0 cat\u00E1logo offline (usando fallback)" }))] }), _jsxs("div", { className: styles.gateGrid, children: [_jsxs("div", { className: styles.gateCard, children: [_jsxs("div", { className: styles.gateCardHeader, children: [_jsx("span", { className: styles.gateName, children: "comment_sentiment" }), _jsx("span", { className: `${styles.gateStatus} ${sentimentBadge.cls}`, children: sentimentBadge.label })] }), sentimentReport && (_jsxs("div", { className: styles.gateMetrics, children: [_jsxs("span", { children: [sentimentReport.passed, "/", sentimentReport.total, " fixtures"] }), _jsx("span", { children: fmtCost(sentimentReport.cost_usd_total) }), _jsxs("span", { children: [sentimentReport.tokens_in_total + sentimentReport.tokens_out_total, " tokens"] }), _jsxs("span", { children: [sentimentReport.duration_ms, "ms"] })] })), _jsx("div", { className: styles.gateActions, children: _jsx("button", { className: styles.gateBtn, onClick: () => onRunEvals("comment_sentiment"), disabled: runningEvals !== null, children: runningEvals === "comment_sentiment" ? "Corriendo..." : "Run sentiment evals" }) }), sentimentReport && !sentimentReport.gate_passed && (_jsx("div", { className: styles.gateFailures, children: sentimentReport.fixtures
                                    .filter(f => !f.passed)
                                    .slice(0, 3)
                                    .map(f => `• ${f.fixture_id}: ${f.failures.slice(0, 2).join(", ")}`)
                                    .join("\n") }))] }), _jsxs("div", { className: styles.gateCard, children: [_jsxs("div", { className: styles.gateCardHeader, children: [_jsx("span", { className: styles.gateName, children: "recommendation_engine" }), _jsx("span", { className: `${styles.gateStatus} ${recBadge.cls}`, children: recBadge.label })] }), recReport && (_jsxs("div", { className: styles.gateMetrics, children: [_jsxs("span", { children: [recReport.passed, "/", recReport.total, " fixtures"] }), _jsx("span", { children: fmtCost(recReport.cost_usd_total) }), _jsxs("span", { children: [recReport.tokens_in_total + recReport.tokens_out_total, " tokens"] }), _jsxs("span", { children: [recReport.duration_ms, "ms"] })] })), _jsxs("div", { className: styles.gateActions, children: [_jsx("button", { className: styles.gateBtn, onClick: () => onRunEvals("recommendation_engine"), disabled: runningEvals !== null, children: runningEvals === "recommendation_engine" ? "Corriendo..." : "Run rec evals" }), _jsx("button", { className: styles.gateBtn, onClick: () => onGenerateRecs(false), disabled: generatingRecs, title: recGateFailed ? "El eval gate no pasó — se bloquea por default" : "", children: generatingRecs ? "Generando..." : "Generate recommendations" }), recGateFailed && (_jsx("button", { className: `${styles.gateBtn} ${styles.danger}`, onClick: () => onGenerateRecs(true), disabled: generatingRecs, title: "Bypassa el gate (solo para debug)", children: "Force unsafe" }))] })] })] }), lastRecRun && (_jsxs("div", { className: styles.gateMetrics, style: { marginTop: 8 }, children: [_jsxs("span", { children: ["\u00DAltima generaci\u00F3n: ", lastRecRun.generated, " OK, ", lastRecRun.rejected, " rechazadas"] }), _jsxs("span", { children: [fmtCost(lastRecRun.cost_usd), " \u00B7 ", lastRecRun.tokens_in + lastRecRun.tokens_out, " tokens"] }), _jsxs("span", { children: ["modelo: ", lastRecRun.model] }), lastRecRun.rejected > 0 && (_jsxs("span", { style: { color: "#fde68a" }, children: ["motivos: ", lastRecRun.rejected_reasons.slice(0, 3).join(", ")] }))] }))] }));
}
function RecommendationFeed({ recommendations, onAcknowledge, ackInFlight }) {
    if (recommendations.length === 0) {
        return (_jsxs("div", { className: styles.empty, children: ["A\u00FAn no hay recomendaciones IA generadas. Corr\u00E9 los evals de recommendation_engine y despu\u00E9s ", _jsx("strong", { children: "Generate recommendations" }), "."] }));
    }
    return (_jsx("div", { className: styles.recList, children: recommendations.map((r) => {
            const prioClass = styles[`priority${r.priority}`] ?? "";
            return (_jsxs("div", { className: `${styles.recItem} ${prioClass} ${r.acknowledged ? styles.ackd : ""}`, children: [_jsxs("div", { className: styles.recHeader, children: [_jsx("span", { className: `${styles.priorityBadge} ${prioClass}`, children: r.priority }), _jsx("span", { className: styles.recCategory, children: r.category }), _jsxs("span", { className: styles.recConfidence, children: ["conf ", (r.confidence * 100).toFixed(0), "%"] }), r.acknowledged ? (_jsxs("span", { className: styles.ackedMark, children: ["\u2713 ack ", r.acknowledged_by, " (", fmtDateTime(r.acknowledged_at), ")"] })) : (_jsx("button", { className: styles.btnAck, onClick: () => onAcknowledge(r.rec_id), disabled: ackInFlight === r.rec_id, children: ackInFlight === r.rec_id ? "..." : "Acknowledge" }))] }), _jsx("div", { className: styles.recAction, children: r.action }), r.rationale && _jsx("div", { className: styles.recRationale, children: r.rationale }), _jsxs("div", { className: styles.recMeta, children: [_jsxs("span", { children: ["ID: ", r.rec_id] }), _jsxs("span", { children: ["modelo: ", r.model] }), _jsxs("span", { children: ["generado: ", fmtDateTime(r.generated_at)] }), _jsxs("span", { className: styles.advisoryBadge, children: ["advisory \u00B7 publish_recommended: ", r.publish_recommended ? "true" : "false"] })] })] }, r.rec_id));
        }) }));
}
// ── Comments Explorer (F2-S UI) ───────────────────────────────────────────────
function sentimentClass(label) {
    switch ((label || "").toLowerCase()) {
        case "positive": return styles.sentimentPositive;
        case "negative": return styles.sentimentNegative;
        case "blocking": return styles.sentimentBlocking;
        case "neutral": return styles.sentimentNeutral;
        default: return styles.sentimentUnanalyzed;
    }
}
function stripHashMarker(text) {
    if (!text)
        return "";
    const idx = text.lastIndexOf("\n[hash:");
    return idx === -1 ? text : text.slice(0, idx);
}
function CommentsExplorer({ adoId, onAdoIdChange, comments, loading, onIndex, onAnalyze, indexing, analyzing, lastIndex, lastAnalyze, }) {
    const unanalyzedCount = comments.filter(c => !c.ai_analyzed).length;
    const sentimentGateFailed = lastAnalyze ? !lastAnalyze.gate_passed : false;
    return (_jsxs("section", { className: styles.commentsPanel, children: [_jsxs("h3", { className: styles.sectionTitle, children: ["\uD83D\uDCAC Comentarios de Work Item", comments.length > 0 && ` (${comments.length})`] }), _jsxs("div", { className: styles.commentsToolbar, children: [_jsx("span", { className: styles.filterLabel, children: "ADO ID:" }), _jsx("input", { type: "number", className: styles.commentsInput, value: adoId ?? "", onChange: (e) => {
                            const v = e.target.value.trim();
                            onAdoIdChange(v ? parseInt(v, 10) : null);
                        }, placeholder: "ej: 12345", min: 1 }), _jsx("button", { className: styles.gateBtn, onClick: onIndex, disabled: !adoId || indexing, children: indexing ? "Indexando..." : "Fetch & index" }), _jsx("button", { className: styles.gateBtn, onClick: () => onAnalyze(false), disabled: unanalyzedCount === 0 || analyzing, title: unanalyzedCount === 0
                            ? "No hay comentarios sin analizar"
                            : `Analizar ${unanalyzedCount} comentario(s)`, children: analyzing ? "Analizando..." : `Analyze sentiment (${unanalyzedCount})` }), sentimentGateFailed && (_jsx("button", { className: `${styles.gateBtn} ${styles.danger}`, onClick: () => onAnalyze(true), disabled: analyzing, title: "Bypassa el gate del eval (debug)", children: "Force unsafe" })), _jsx("span", { className: styles.commentsHint, children: "pii_masked \u00B7 advisory_only" })] }), lastIndex && (_jsx("div", { className: styles.gateMetrics, style: { marginBottom: 8 }, children: _jsxs("span", { children: ["\u00DAltimo index: ", lastIndex.inserted, " nuevos \u00B7 ", lastIndex.skipped_duplicates, " ya indexados \u00B7 ", lastIndex.total_fetched, " tra\u00EDdos de ADO"] }) })), lastAnalyze && (_jsxs("div", { className: styles.gateMetrics, style: { marginBottom: 8 }, children: [_jsxs("span", { children: ["\u00DAltimo analyze: ", lastAnalyze.analyzed, " OK \u00B7 ", lastAnalyze.failures, " fallos \u00B7 costo ", fmtCost(lastAnalyze.cost_usd)] }), !lastAnalyze.gate_passed && (_jsx("span", { style: { color: "#fca5a5" }, children: "\u26A0 eval gate no pas\u00F3 \u2014 el resultado puede no haberse persistido" }))] })), loading ? (_jsx("div", { className: styles.empty, children: "Cargando comentarios..." })) : comments.length === 0 ? (_jsx("div", { className: styles.empty, children: adoId
                    ? `No hay comentarios indexados para ADO ${adoId}. Hacé click en "Fetch & index" para traerlos desde ADO.`
                    : "Ingresá un ADO ID arriba para indexar los comentarios del work item." })) : (_jsx("div", { className: styles.commentsList, children: comments.map((c) => {
                    const sCls = sentimentClass(c.sentiment_label);
                    return (_jsxs("div", { className: `${styles.commentItem} ${sCls} ${!c.ai_analyzed ? styles.unanalyzed : ""}`, children: [_jsxs("div", { className: styles.commentHeader, children: [_jsx("span", { className: `${styles.sentimentBadge} ${sCls}`, children: c.ai_analyzed
                                            ? `${c.sentiment_label ?? "neutral"} ${c.sentiment_score != null ? `(${(c.sentiment_score * 100).toFixed(0)}%)` : ""}`
                                            : "unanalyzed" }), _jsx("span", { children: c.author ?? "?" }), _jsx("span", { children: c.comment_date ?? "—" })] }), _jsx("div", { className: styles.commentText, children: stripHashMarker(c.text_plain) }), _jsxs("div", { className: styles.commentMeta, children: [_jsxs("span", { children: ["id interno: ", c.id] }), _jsxs("span", { children: ["indexed: ", fmtDateTime(c.indexed_at)] })] })] }, c.id));
                }) }))] }));
}
// ── Page ──────────────────────────────────────────────────────────────────────
const MODEL_LS_KEY = "pm.selectedModel";
function readPersistedModel() {
    if (typeof window === "undefined")
        return null;
    try {
        const v = window.localStorage.getItem(MODEL_LS_KEY);
        return v && v.length > 0 ? v : null;
    }
    catch {
        return null;
    }
}
function persistModel(model) {
    if (typeof window === "undefined")
        return;
    try {
        window.localStorage.setItem(MODEL_LS_KEY, model);
    }
    catch {
        /* ignore */
    }
}
export default function PMCommandCenter() {
    const qc = useQueryClient();
    const [severityFilter, setSeverityFilter] = useState("ALL");
    const [showAcked, setShowAcked] = useState(false);
    const [syncError, setSyncError] = useState(null);
    const [aiWindow, setAiWindow] = useState(24);
    const [selectedModel, setSelectedModel] = useState(readPersistedModel());
    const modelsQuery = useQuery({
        queryKey: ["pm.ai.models"],
        queryFn: () => PmApi.aiModels(),
        staleTime: 5 * 60_000,
    });
    // Cuando llega la lista de modelos: si no hay selección o la persistida ya
    // no existe en la lista, caer al default que reporta el backend.
    React.useEffect(() => {
        const report = modelsQuery.data;
        if (!report)
            return;
        const availableIds = new Set(report.models.map((m) => m.id));
        if (!selectedModel || !availableIds.has(selectedModel)) {
            setSelectedModel(report.default_model);
            persistModel(report.default_model);
        }
    }, [modelsQuery.data, selectedModel]);
    const activeModel = selectedModel ?? modelsQuery.data?.default_model ?? "mock-1.0";
    const handleModelChange = (model) => {
        setSelectedModel(model);
        persistModel(model);
    };
    const sprintQuery = useQuery({
        queryKey: ["pm.sprint.current"],
        queryFn: async () => {
            try {
                return await PmApi.sprintCurrent();
            }
            catch (e) {
                // 404 NO_SNAPSHOT no es error real — devolvemos null
                const msg = e instanceof Error ? e.message : String(e);
                if (msg.includes("404"))
                    return null;
                throw e;
            }
        },
        staleTime: 30_000,
    });
    const risksQuery = useQuery({
        queryKey: ["pm.risks", severityFilter, showAcked],
        queryFn: async () => {
            const params = {};
            if (severityFilter !== "ALL")
                params.severity = severityFilter;
            if (!showAcked)
                params.acknowledged = false;
            const res = await PmApi.listRisks(params);
            return res.risks;
        },
        staleTime: 30_000,
    });
    const syncMutation = useMutation({
        mutationFn: () => PmApi.syncAdo({}),
        onSuccess: () => {
            setSyncError(null);
            qc.invalidateQueries({ queryKey: ["pm.sprint.current"] });
            qc.invalidateQueries({ queryKey: ["pm.risks"] });
        },
        onError: (e) => {
            setSyncError(e instanceof Error ? e.message : String(e));
        },
    });
    const ackMutation = useMutation({
        mutationFn: (riskId) => PmApi.acknowledgeRisk(riskId),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["pm.risks"] });
        },
    });
    const aiUsageQuery = useQuery({
        queryKey: ["pm.ai.usage", aiWindow],
        queryFn: () => PmApi.aiUsage({ since_hours: aiWindow }),
        staleTime: 15_000,
        refetchInterval: 30_000,
    });
    const [sentimentReport, setSentimentReport] = useState(null);
    const [recReport, setRecReport] = useState(null);
    const [lastRecRun, setLastRecRun] = useState(null);
    const evalsMutation = useMutation({
        mutationFn: (component) => PmApi.runEvals({ component, model: activeModel }),
        onSuccess: (report) => {
            if (report.component === "comment_sentiment")
                setSentimentReport(report);
            else if (report.component === "recommendation_engine")
                setRecReport(report);
            qc.invalidateQueries({ queryKey: ["pm.ai.usage"] });
        },
    });
    const generateRecsMutation = useMutation({
        mutationFn: (forceUnsafe) => PmApi.generateRecommendations({ force_unsafe: forceUnsafe, model: activeModel }),
        onSuccess: (result) => {
            setLastRecRun(result);
            qc.invalidateQueries({ queryKey: ["pm.recommendations"] });
            qc.invalidateQueries({ queryKey: ["pm.ai.usage"] });
        },
        onError: (e) => {
            // El backend retorna 412 cuando el gate no pasa — capturamos el mensaje
            console.warn("generate recommendations failed:", e);
        },
    });
    const recsQuery = useQuery({
        queryKey: ["pm.recommendations"],
        queryFn: () => PmApi.listRecommendations(),
        staleTime: 30_000,
    });
    const ackRecMutation = useMutation({
        mutationFn: (recId) => PmApi.acknowledgeRecommendation(recId),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["pm.recommendations"] });
        },
    });
    // ── comments explorer ──────────────────────────────────────────────────────
    const [commentsAdoId, setCommentsAdoId] = useState(null);
    const [lastIndex, setLastIndex] = useState(null);
    const [lastAnalyze, setLastAnalyze] = useState(null);
    const commentsQuery = useQuery({
        queryKey: ["pm.comments", commentsAdoId],
        queryFn: () => PmApi.listComments(commentsAdoId, 50),
        enabled: commentsAdoId !== null && commentsAdoId > 0,
        staleTime: 15_000,
    });
    const indexMutation = useMutation({
        mutationFn: (adoId) => PmApi.indexComments({ ado_ids: [adoId], top_per_item: 50 }),
        onSuccess: (result) => {
            setLastIndex({
                inserted: result.inserted,
                skipped_duplicates: result.skipped_duplicates,
                total_fetched: result.total_fetched,
            });
            qc.invalidateQueries({ queryKey: ["pm.comments"] });
        },
    });
    const sentimentMutation = useMutation({
        mutationFn: ({ ids, force }) => PmApi.analyzeSentiment({
            comment_ids: ids,
            model: activeModel,
            force_unsafe: force,
        }),
        onSuccess: (result) => {
            setLastAnalyze({
                analyzed: result.analyzed,
                failures: result.failures,
                gate_passed: result.gate_passed,
                cost_usd: result.cost_usd,
            });
            qc.invalidateQueries({ queryKey: ["pm.comments"] });
            qc.invalidateQueries({ queryKey: ["pm.ai.usage"] });
        },
        onError: (e) => {
            console.warn("sentiment analyze failed:", e);
            setLastAnalyze({ analyzed: 0, failures: 0, gate_passed: false, cost_usd: 0 });
        },
    });
    const snapshot = sprintQuery.data?.snapshot ?? null;
    const capturedAt = sprintQuery.data?.snapshot?.captured_at ?? null;
    const risks = risksQuery.data ?? [];
    const summary = useMemo(() => {
        const highCount = risks.filter(r => r.severity === "HIGH" || r.severity === "CRITICAL").length;
        const mediumCount = risks.filter(r => r.severity === "MEDIUM").length;
        return { highCount, mediumCount };
    }, [risks]);
    return (_jsxs("div", { className: styles.page, children: [_jsxs("div", { className: styles.header, children: [_jsx("h1", { className: styles.title, children: "\uD83D\uDCCA PM Command Center" }), _jsx("span", { className: styles.subtitle, children: "Fase 1 MVP \u00B7 sin IA \u00B7 azure_devops \u00FAnicamente" }), _jsx("span", { className: styles.advisoryBadge, children: "advisory_only" }), _jsxs("div", { className: styles.headerActions, children: [_jsx("button", { className: styles.btnPrimary, onClick: () => syncMutation.mutate(), disabled: syncMutation.isPending, children: syncMutation.isPending ? "Sincronizando..." : "↻ Sync ADO" }), _jsx("button", { className: styles.btnGhost, onClick: () => {
                                    qc.invalidateQueries({ queryKey: ["pm.sprint.current"] });
                                    qc.invalidateQueries({ queryKey: ["pm.risks"] });
                                }, children: "Refresh" })] })] }), _jsxs("div", { className: styles.content, children: [syncError && (_jsxs("div", { className: styles.bannerError, children: [_jsx("strong", { children: "Sync fall\u00F3:" }), " ", syncError] })), !snapshot && !sprintQuery.isLoading && (_jsxs("div", { className: styles.bannerInfo, children: ["No hay snapshots PM para este proyecto. Hac\u00E9 click en ", _jsx("strong", { children: "Sync ADO" }), " para traer el sprint actual y calcular KPIs/riesgos determin\u00EDsticos."] })), sprintQuery.isLoading && _jsx("div", { className: styles.empty, children: "Cargando sprint actual..." }), (snapshot || sprintQuery.isLoading) && (_jsx(SprintHealthCard, { snapshot: snapshot, capturedAt: capturedAt })), _jsxs("section", { className: styles.riskSection, children: [_jsxs("h3", { className: styles.sectionTitle, children: ["Riesgos detectados (", summary.highCount, " altos \u00B7 ", summary.mediumCount, " medios)"] }), _jsxs("div", { className: styles.filterBar, children: [_jsx("span", { className: styles.filterLabel, children: "Severidad:" }), _jsxs("select", { className: styles.filterSelect, value: severityFilter, onChange: (e) => setSeverityFilter(e.target.value), children: [_jsx("option", { value: "ALL", children: "Todas" }), _jsx("option", { value: "CRITICAL", children: "Critical" }), _jsx("option", { value: "HIGH", children: "High" }), _jsx("option", { value: "MEDIUM", children: "Medium" }), _jsx("option", { value: "LOW", children: "Low" })] }), _jsxs("label", { className: styles.filterLabel, children: [_jsx("input", { type: "checkbox", checked: showAcked, onChange: (e) => setShowAcked(e.target.checked), style: { marginRight: 4 } }), "Mostrar acknowledged"] }), _jsx("span", { className: styles.advisoryBadge, children: "ai_enriched: false \u00B7 reglas deterministas" })] }), risksQuery.isLoading ? (_jsx("div", { className: styles.empty, children: "Cargando riesgos..." })) : (_jsx(RiskFeed, { risks: risks, onAcknowledge: (id) => ackMutation.mutate(id), ackInFlight: ackMutation.isPending ? ackMutation.variables ?? null : null }))] }), _jsx(AIControlPanel, { sentimentReport: sentimentReport, recReport: recReport, onRunEvals: (c) => evalsMutation.mutate(c), onGenerateRecs: (force) => generateRecsMutation.mutate(force), runningEvals: evalsMutation.isPending ? (evalsMutation.variables ?? null) : null, generatingRecs: generateRecsMutation.isPending, lastRecRun: lastRecRun, modelsReport: modelsQuery.data ?? null, modelsLoading: modelsQuery.isLoading, selectedModel: activeModel, onModelChange: handleModelChange }), _jsxs("section", { className: styles.recPanel, children: [_jsxs("h3", { className: styles.sectionTitle, children: ["Recomendaciones IA generadas", recsQuery.data && ` (${recsQuery.data.count})`] }), recsQuery.isLoading ? (_jsx("div", { className: styles.empty, children: "Cargando recomendaciones..." })) : (_jsx(RecommendationFeed, { recommendations: recsQuery.data?.recommendations ?? [], onAcknowledge: (id) => ackRecMutation.mutate(id), ackInFlight: ackRecMutation.isPending ? (ackRecMutation.variables ?? null) : null }))] }), _jsx(CommentsExplorer, { adoId: commentsAdoId, onAdoIdChange: setCommentsAdoId, comments: commentsQuery.data?.comments ?? [], loading: commentsQuery.isLoading, indexing: indexMutation.isPending, analyzing: sentimentMutation.isPending, lastIndex: lastIndex, lastAnalyze: lastAnalyze, onIndex: () => {
                            if (commentsAdoId !== null && commentsAdoId > 0) {
                                indexMutation.mutate(commentsAdoId);
                            }
                        }, onAnalyze: (force) => {
                            const unanalyzed = (commentsQuery.data?.comments ?? [])
                                .filter((c) => !c.ai_analyzed)
                                .map((c) => c.id);
                            if (unanalyzed.length > 0) {
                                sentimentMutation.mutate({ ids: unanalyzed, force });
                            }
                        } }), _jsx(AIUsagePanel, { report: aiUsageQuery.data ?? null, windowHours: aiWindow, onWindowChange: setAiWindow, loading: aiUsageQuery.isLoading })] })] }));
}
