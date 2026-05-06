import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { SystemLogs } from "../api/endpoints";
import styles from "./SystemLogsPage.module.css";
const PAGE_SIZE = 100;
const LEVEL_OPTIONS = ["", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];
function levelClass(level) {
    const map = {
        DEBUG: styles.lvlDEBUG,
        INFO: styles.lvlINFO,
        WARNING: styles.lvlWARNING,
        ERROR: styles.lvlERROR,
        CRITICAL: styles.lvlCRITICAL,
    };
    return map[level] ?? styles.lvlINFO;
}
function fmtTs(ts) {
    try {
        const d = new Date(ts);
        return d.toLocaleString("es-AR", { hour12: false });
    }
    catch {
        return ts;
    }
}
function fmtMs(ms) {
    if (ms == null)
        return "—";
    if (ms < 1000)
        return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
}
function DetailModal({ log, onClose }) {
    const metaFields = [
        ["ID", log.id],
        ["Timestamp", fmtTs(log.timestamp)],
        ["Level", log.level],
        ["Source", log.source],
        ["Action", log.action],
        ["Execution ID", log.execution_id ?? "—"],
        ["Ticket ID", log.ticket_id ?? "—"],
        ["User", log.user ?? "—"],
        ["Request ID", log.request_id ?? "—"],
        ["Method", log.method ?? "—"],
        ["Endpoint", log.endpoint ?? "—"],
        ["Status Code", log.status_code ?? "—"],
        ["Duration", fmtMs(log.duration_ms)],
        ["Tags", log.tags?.join(", ") || "—"],
    ];
    return (_jsx("div", { className: styles.modalOverlay, onClick: onClose, children: _jsxs("div", { className: styles.modal, onClick: (e) => e.stopPropagation(), children: [_jsxs("div", { className: styles.modalHeader, children: [_jsx("span", { className: `${styles.lvl} ${levelClass(log.level)}`, children: log.level }), _jsxs("span", { className: styles.modalTitle, children: [log.source, " \u203A ", log.action] }), _jsx("button", { className: styles.modalClose, onClick: onClose, children: "\u00D7" })] }), _jsxs("div", { className: styles.modalBody, children: [_jsx("div", { className: styles.metaGrid, children: metaFields.map(([label, value]) => (_jsxs("div", { className: styles.metaItem, children: [_jsx("div", { className: styles.metaLabel, children: label }), _jsx("div", { className: styles.metaValue, children: String(value) })] }, label))) }), log.error && (_jsxs("div", { children: [_jsx("p", { className: styles.sectionTitle, children: "Error" }), _jsxs("div", { className: styles.errorBlock, children: [_jsxs("strong", { children: [log.error.type, ": ", log.error.message] }), "\n\n", log.error.traceback] })] })), log.input != null && (_jsxs("div", { children: [_jsx("p", { className: styles.sectionTitle, children: "Input" }), _jsx("pre", { className: styles.codeBlock, children: JSON.stringify(log.input, null, 2) })] })), log.output != null && (_jsxs("div", { children: [_jsx("p", { className: styles.sectionTitle, children: "Output" }), _jsx("pre", { className: styles.codeBlock, children: JSON.stringify(log.output, null, 2) })] })), log.context && Object.keys(log.context).length > 0 && (_jsxs("div", { children: [_jsx("p", { className: styles.sectionTitle, children: "Context" }), _jsx("pre", { className: styles.codeBlock, children: JSON.stringify(log.context, null, 2) })] }))] })] }) }));
}
// ── Main Page ───────────────────────────────────────────────────────────────
export default function SystemLogsPage() {
    const [filters, setFilters] = useState({
        level: "",
        source: "",
        action: "",
        q: "",
        execution_id: "",
        ticket_id: "",
        from: "",
        to: "",
    });
    const [offset, setOffset] = useState(0);
    const [selected, setSelected] = useState(null);
    const queryParams = {
        level: filters.level || undefined,
        source: filters.source || undefined,
        action: filters.action || undefined,
        q: filters.q || undefined,
        execution_id: filters.execution_id ? parseInt(filters.execution_id) : undefined,
        ticket_id: filters.ticket_id ? parseInt(filters.ticket_id) : undefined,
        from: filters.from || undefined,
        to: filters.to || undefined,
        limit: PAGE_SIZE,
        offset,
    };
    const { data, isLoading, isFetching } = useQuery({
        queryKey: ["system-logs", queryParams],
        queryFn: () => SystemLogs.list(queryParams),
        staleTime: 10_000,
        refetchInterval: 30_000,
    });
    const { data: stats } = useQuery({
        queryKey: ["system-logs-stats"],
        queryFn: () => SystemLogs.stats(),
        staleTime: 30_000,
        refetchInterval: 60_000,
    });
    const setFilter = useCallback((key, value) => {
        setFilters((f) => ({ ...f, [key]: value }));
        setOffset(0);
    }, []);
    const clearFilters = () => {
        setFilters({ level: "", source: "", action: "", q: "", execution_id: "", ticket_id: "", from: "", to: "" });
        setOffset(0);
    };
    const total = data?.total ?? 0;
    const items = data?.items ?? [];
    const totalPages = Math.ceil(total / PAGE_SIZE);
    const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
    const exportUrl = SystemLogs.exportUrl({ format: "json", level: filters.level || undefined, source: filters.source || undefined });
    return (_jsxs("div", { className: styles.page, children: [_jsxs("div", { className: styles.header, children: [_jsx("h2", { className: styles.title, children: "\uD83D\uDCCB System Logs" }), stats && (_jsxs("div", { className: styles.stats, children: [_jsxs("span", { className: `${styles.statBadge} ${styles.error}`, children: ["ERR ", stats.by_level["ERROR"] ?? 0] }), _jsxs("span", { className: `${styles.statBadge} ${styles.warning}`, children: ["WARN ", stats.by_level["WARNING"] ?? 0] }), _jsxs("span", { className: `${styles.statBadge} ${styles.info}`, children: ["Total ", stats.total.toLocaleString()] })] })), _jsx("span", { className: styles.spacer }), _jsx("a", { href: exportUrl, download: "stacky_logs.json", className: styles.exportBtn, target: "_blank", rel: "noopener noreferrer", children: "\u2193 Export JSON" }), _jsx("a", { href: SystemLogs.exportUrl({ format: "csv" }), download: "stacky_logs.csv", className: styles.exportBtn, target: "_blank", rel: "noopener noreferrer", children: "\u2193 Export CSV" })] }), _jsxs("div", { className: styles.filters, children: [_jsx("select", { className: styles.filterSelect, value: filters.level, onChange: (e) => setFilter("level", e.target.value), children: LEVEL_OPTIONS.map((l) => (_jsx("option", { value: l, children: l || "All levels" }, l))) }), _jsx("input", { className: `${styles.filterInput} ${styles.wide}`, placeholder: "Source (e.g. agent_runner)", value: filters.source, onChange: (e) => setFilter("source", e.target.value) }), _jsx("input", { className: `${styles.filterInput} ${styles.wide}`, placeholder: "Action (e.g. agent_started)", value: filters.action, onChange: (e) => setFilter("action", e.target.value) }), _jsx("input", { className: `${styles.filterInput} ${styles.wide}`, placeholder: "Search text...", value: filters.q, onChange: (e) => setFilter("q", e.target.value) }), _jsx("input", { className: `${styles.filterInput} ${styles.narrow}`, placeholder: "Exec ID", type: "number", value: filters.execution_id, onChange: (e) => setFilter("execution_id", e.target.value) }), _jsx("input", { className: `${styles.filterInput} ${styles.narrow}`, placeholder: "Ticket ID", type: "number", value: filters.ticket_id, onChange: (e) => setFilter("ticket_id", e.target.value) }), _jsx("input", { className: styles.filterInput, type: "datetime-local", value: filters.from, onChange: (e) => setFilter("from", e.target.value), title: "From date" }), _jsx("input", { className: styles.filterInput, type: "datetime-local", value: filters.to, onChange: (e) => setFilter("to", e.target.value), title: "To date" }), _jsx("button", { className: styles.clearBtn, onClick: clearFilters, children: "Clear" })] }), _jsx("div", { className: styles.tableWrap, children: isLoading ? (_jsx("div", { className: styles.empty, children: "Loading logs\u2026" })) : items.length === 0 ? (_jsx("div", { className: styles.empty, children: "No logs match the current filters." })) : (_jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Level" }), _jsx("th", { children: "Timestamp" }), _jsx("th", { children: "Source" }), _jsx("th", { children: "Action" }), _jsx("th", { children: "Exec ID" }), _jsx("th", { children: "Ticket" }), _jsx("th", { children: "User" }), _jsx("th", { children: "Method" }), _jsx("th", { children: "Endpoint" }), _jsx("th", { children: "Status" }), _jsx("th", { children: "Duration" })] }) }), _jsx("tbody", { children: items.map((log) => (_jsxs("tr", { onClick: () => setSelected(log), children: [_jsx("td", { children: _jsx("span", { className: `${styles.lvl} ${levelClass(log.level)}`, children: log.level }) }), _jsx("td", { title: log.timestamp, children: fmtTs(log.timestamp) }), _jsx("td", { title: log.source, children: log.source }), _jsx("td", { title: log.action, children: log.action }), _jsx("td", { children: log.execution_id ?? "—" }), _jsx("td", { children: log.ticket_id ?? "—" }), _jsx("td", { children: log.user ?? "—" }), _jsx("td", { children: log.method ?? "—" }), _jsx("td", { title: log.endpoint ?? "", children: log.endpoint ?? "—" }), _jsx("td", { style: { color: log.status_code && log.status_code >= 400 ? "#f87171" : undefined }, children: log.status_code ?? "—" }), _jsx("td", { children: fmtMs(log.duration_ms) })] }, log.id))) })] })) }), _jsxs("div", { className: styles.pagination, children: [_jsx("button", { className: styles.pageBtn, disabled: offset === 0, onClick: () => setOffset(Math.max(0, offset - PAGE_SIZE)), children: "\u2190 Prev" }), _jsxs("span", { children: ["Page ", currentPage, " of ", totalPages || 1] }), _jsx("button", { className: styles.pageBtn, disabled: offset + PAGE_SIZE >= total, onClick: () => setOffset(offset + PAGE_SIZE), children: "Next \u2192" }), isFetching && _jsx("span", { style: { color: "#a78bfa", fontSize: 11 }, children: "Refreshing\u2026" }), _jsxs("span", { className: styles.total, children: [total.toLocaleString(), " total events"] })] }), selected && (_jsx(DetailModal, { log: selected, onClose: () => setSelected(null) }))] }));
}
