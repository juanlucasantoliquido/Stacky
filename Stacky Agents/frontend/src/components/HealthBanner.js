import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./HealthBanner.module.css";
const POLL_MS = 30_000;
const DISMISS_TTL_MS = 30 * 60 * 1000;
function loadDismissed() {
    try {
        const raw = localStorage.getItem("stacky.healthBanner.dismissed");
        if (!raw)
            return null;
        const parsed = JSON.parse(raw);
        if (Date.now() > parsed.until) {
            localStorage.removeItem("stacky.healthBanner.dismissed");
            return null;
        }
        return parsed;
    }
    catch {
        return null;
    }
}
function persistDismissed(checkId) {
    const state = { checkId, until: Date.now() + DISMISS_TTL_MS };
    localStorage.setItem("stacky.healthBanner.dismissed", JSON.stringify(state));
}
const FIX_HINT = {
    tracker: { label: "Abrir configuración", tab: "settings" },
    vscode_bridge: { label: "Abrir Diagnóstico", tab: "diagnostics" },
    vscode_vsix: { label: "Abrir Diagnóstico", tab: "diagnostics" },
    gh_auth: { label: "Abrir Diagnóstico", tab: "diagnostics" },
    database: { label: "Abrir Diagnóstico", tab: "diagnostics" },
};
export default function HealthBanner() {
    const [worst, setWorst] = useState(null);
    const [expanded, setExpanded] = useState(false);
    useEffect(() => {
        let cancelled = false;
        let timer;
        async function poll() {
            try {
                const data = await api.get("/api/diag/local");
                if (cancelled)
                    return;
                const errored = data.checks.find((c) => c.status === "error") ?? null;
                const warned = errored ? null : data.checks.find((c) => c.status === "warning") ?? null;
                const next = errored ?? warned;
                const dismissed = loadDismissed();
                if (next && dismissed && dismissed.checkId === next.id) {
                    setWorst(null);
                }
                else {
                    setWorst(next);
                }
            }
            catch {
                if (!cancelled) {
                    setWorst({
                        id: "backend",
                        label: "Backend",
                        status: "error",
                        message: "El backend no responde — revisá que esté corriendo.",
                    });
                }
            }
            finally {
                if (!cancelled) {
                    timer = window.setTimeout(poll, POLL_MS);
                }
            }
        }
        poll();
        return () => {
            cancelled = true;
            if (timer !== undefined)
                window.clearTimeout(timer);
        };
    }, []);
    if (!worst)
        return null;
    const hint = FIX_HINT[worst.id];
    const goTab = () => {
        if (!hint?.tab)
            return;
        const path = hint.tab === "settings" ? "/settings" : `/${hint.tab}`;
        window.history.pushState({}, "", path);
        window.dispatchEvent(new PopStateEvent("popstate"));
    };
    return (_jsxs("div", { className: `${styles.banner} ${worst.status === "error" ? styles.error : styles.warning}`, role: "alert", children: [_jsx("span", { className: styles.icon, "aria-hidden": "true", children: worst.status === "error" ? "⚠" : "⚡" }), _jsxs("div", { className: styles.body, children: [_jsx("strong", { className: styles.title, children: worst.label }), _jsx("span", { className: styles.msg, children: worst.message }), expanded && worst.detail ? (_jsx("pre", { className: styles.detail, children: JSON.stringify(worst.detail, null, 2) })) : null] }), _jsxs("div", { className: styles.actions, children: [hint?.tab ? (_jsx("button", { className: styles.fixBtn, onClick: goTab, children: hint.label })) : null, _jsx("button", { className: styles.detailBtn, onClick: () => setExpanded((v) => !v), "aria-expanded": expanded, children: expanded ? "Menos" : "Detalles" }), _jsx("button", { className: styles.dismissBtn, onClick: () => {
                            persistDismissed(worst.id);
                            setWorst(null);
                        }, "aria-label": "Ocultar por 30 minutos", title: "Ocultar por 30 minutos", children: "\u00D7" })] })] }));
}
