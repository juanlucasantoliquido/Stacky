import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, CheckCircle2, DatabaseBackup, Download, RefreshCcw, XCircle, } from "lucide-react";
import { LocalDiagnostics } from "../api/endpoints";
import styles from "./DiagnosticsPage.module.css";
const STATUS_LABEL = {
    ok: "OK",
    warning: "Atención",
    error: "Error",
};
function StatusIcon({ status }) {
    if (status === "ok")
        return _jsx(CheckCircle2, { size: 18, className: styles.okIcon, "aria-hidden": "true" });
    if (status === "warning")
        return _jsx(AlertTriangle, { size: 18, className: styles.warnIcon, "aria-hidden": "true" });
    return _jsx(XCircle, { size: 18, className: styles.errorIcon, "aria-hidden": "true" });
}
function fmtBytes(value) {
    if (value >= 1024 * 1024)
        return `${(value / (1024 * 1024)).toFixed(1)} MB`;
    if (value >= 1024)
        return `${(value / 1024).toFixed(1)} KB`;
    return `${value} B`;
}
function fmtDate(value) {
    const d = new Date(value);
    if (Number.isNaN(d.getTime()))
        return value;
    return d.toLocaleString();
}
function DetailBlock({ detail }) {
    if (!detail)
        return null;
    const text = typeof detail === "string" ? detail : JSON.stringify(detail, null, 2);
    return _jsx("pre", { className: styles.detail, children: text });
}
export default function DiagnosticsPage() {
    const queryClient = useQueryClient();
    const diagnostics = useQuery({
        queryKey: ["local-diagnostics"],
        queryFn: LocalDiagnostics.get,
        refetchInterval: 30_000,
    });
    const backup = useMutation({
        mutationFn: LocalDiagnostics.runBackup,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ["local-diagnostics"] }),
    });
    const data = diagnostics.data;
    return (_jsxs("main", { className: styles.page, children: [_jsxs("header", { className: styles.header, children: [_jsxs("div", { className: styles.titleBlock, children: [_jsx("h2", { className: styles.title, children: "Diagn\u00F3stico local" }), _jsx("span", { className: styles.subtitle, children: data ? `Último chequeo ${fmtDate(data.checked_at)} · ${data.duration_ms} ms` : "Chequeando entorno local" })] }), data && (_jsxs("div", { className: styles.summary, "aria-label": "Resumen de diagn\u00F3stico", children: [_jsxs("span", { className: `${styles.summaryBadge} ${styles.okBadge}`, children: [data.summary.ok, " OK"] }), _jsxs("span", { className: `${styles.summaryBadge} ${styles.warnBadge}`, children: [data.summary.warning, " atenci\u00F3n"] }), _jsxs("span", { className: `${styles.summaryBadge} ${styles.errorBadge}`, children: [data.summary.error, " error"] })] })), _jsx("span", { className: styles.spacer }), _jsx("a", { href: LocalDiagnostics.exportLogsUrl(), className: styles.iconButton, title: "Exportar logs", "aria-label": "Exportar logs", children: _jsx(Download, { size: 16 }) }), _jsx("button", { className: styles.iconButton, onClick: () => diagnostics.refetch(), disabled: diagnostics.isFetching, title: "Actualizar diagn\u00F3stico", "aria-label": "Actualizar diagn\u00F3stico", children: _jsx(RefreshCcw, { size: 16 }) })] }), diagnostics.isError && (_jsxs("section", { className: styles.errorPanel, children: [_jsx(XCircle, { size: 18 }), _jsx("span", { children: diagnostics.error instanceof Error ? diagnostics.error.message : "No se pudo cargar el diagnóstico." })] })), _jsxs("section", { className: styles.checkGrid, children: [diagnostics.isLoading &&
                        Array.from({ length: 6 }).map((_, index) => (_jsxs("article", { className: styles.checkCard, children: [_jsx("span", { className: styles.skeletonIcon }), _jsxs("div", { className: styles.skeletonLines, children: [_jsx("span", {}), _jsx("span", {})] })] }, index))), data?.checks.map((check) => (_jsxs("article", { className: styles.checkCard, children: [_jsxs("div", { className: styles.checkHeader, children: [_jsx(StatusIcon, { status: check.status }), _jsxs("div", { className: styles.checkTitleBlock, children: [_jsx("h3", { className: styles.checkTitle, children: check.label }), _jsx("span", { className: `${styles.statusPill} ${styles[check.status]}`, children: STATUS_LABEL[check.status] })] })] }), _jsx("p", { className: styles.checkMessage, children: check.message }), _jsx(DetailBlock, { detail: check.detail })] }, check.id)))] }), data && (_jsxs("section", { className: styles.opsGrid, children: [_jsxs("div", { className: styles.opsPanel, children: [_jsxs("div", { className: styles.panelHeader, children: [_jsx(Activity, { size: 16 }), _jsx("h3", { children: "Logs locales" }), _jsxs("a", { href: LocalDiagnostics.exportLogsUrl(), className: styles.textButton, title: "Exportar logs", "aria-label": "Exportar logs", children: [_jsx(Download, { size: 14 }), "Exportar ZIP"] })] }), _jsx("div", { className: styles.pathLine, children: data.logs.directory }), data.logs.recent_files.length === 0 ? (_jsx("div", { className: styles.empty, children: "Sin archivos recientes." })) : (_jsx("ul", { className: styles.fileList, children: data.logs.recent_files.map((path) => (_jsx("li", { children: path }, path))) }))] }), _jsxs("div", { className: styles.opsPanel, children: [_jsxs("div", { className: styles.panelHeader, children: [_jsx(DatabaseBackup, { size: 16 }), _jsx("h3", { children: "Backups DB" }), _jsxs("button", { className: styles.textButton, onClick: () => backup.mutate(), disabled: backup.isPending, title: "Ejecutar backup", "aria-label": "Ejecutar backup", children: [_jsx(DatabaseBackup, { size: 14 }), backup.isPending ? "Ejecutando" : "Ejecutar"] })] }), backup.data && (_jsx("div", { className: backup.data.ok ? styles.inlineOk : styles.inlineError, children: backup.data.skipped ? backup.data.reason : backup.data.backup_path })), data.backups.length === 0 ? (_jsx("div", { className: styles.empty, children: "Sin backups registrados." })) : (_jsx("ul", { className: styles.backupList, children: data.backups.map((item) => (_jsxs("li", { children: [_jsx("span", { children: item.filename }), _jsx("strong", { children: fmtBytes(item.size_bytes) }), _jsx("em", { children: fmtDate(item.created_at) })] }, item.path))) }))] })] }))] }));
}
