import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import styles from "./SyncStatusBar.module.css";
function formatSeconds(sec) {
    if (sec < 60)
        return `${sec}s`;
    const min = Math.floor(sec / 60);
    const s = sec % 60;
    return s > 0 ? `${min}m ${s}s` : `${min}m`;
}
export function SyncStatusBar({ lastSyncedAt, secondsSinceSync, isSyncing, syncError, onSyncClick, isStale, intervalMs = 45_000, }) {
    const agingThresholdSec = 60;
    if (isSyncing) {
        return (_jsx("div", { className: styles.wrap, children: _jsxs("div", { className: `${styles.bar} ${styles.toneNeutral}`, children: [_jsx("span", { className: styles.spinner }), _jsx("span", { className: styles.label, children: "Sincronizando con ADO\u2026" })] }) }));
    }
    if (syncError) {
        return (_jsx("div", { className: styles.wrap, children: _jsxs("div", { className: `${styles.bar} ${styles.toneDanger}`, children: [_jsx("span", { className: `${styles.dot} ${styles.red}` }), _jsx("span", { className: `${styles.label} ${styles.labelError}`, title: syncError, children: "Error de sincronizaci\u00F3n" }), _jsx("button", { className: styles.btn, onClick: onSyncClick, children: "Reintentar" })] }) }));
    }
    if (!lastSyncedAt || secondsSinceSync === null) {
        return (_jsx("div", { className: styles.wrap, children: _jsxs("div", { className: `${styles.bar} ${styles.toneNeutral}`, children: [_jsx("span", { className: `${styles.dot} ${styles.yellow}` }), _jsx("span", { className: styles.label, children: "Sin sincronizar" }), _jsx("button", { className: styles.btn, onClick: onSyncClick, children: "Sincronizar" })] }) }));
    }
    if (isStale) {
        return (_jsx("div", { className: styles.wrap, children: _jsxs("div", { className: `${styles.bar} ${styles.toneWarning}`, children: [_jsx("span", { className: `${styles.dot} ${styles.red}` }), _jsxs("span", { className: `${styles.label} ${styles.labelStale}`, children: ["Sin actualizar hace ", formatSeconds(secondsSinceSync)] }), _jsx("button", { className: styles.btn, onClick: onSyncClick, children: "Actualizar" })] }) }));
    }
    const dotColor = secondsSinceSync < agingThresholdSec ? styles.green : styles.yellow;
    return (_jsx("div", { className: styles.wrap, children: _jsxs("div", { className: `${styles.bar} ${styles.toneNeutral}`, children: [_jsx("span", { className: `${styles.dot} ${dotColor}` }), _jsxs("span", { className: styles.label, children: ["Sincronizado hace ", formatSeconds(secondsSinceSync)] }), _jsx("button", { className: styles.btn, onClick: onSyncClick, children: "Sincronizar" })] }) }));
}
export default SyncStatusBar;
