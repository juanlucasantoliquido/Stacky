import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./DailyStandupModal.module.css";
const SHOWN_KEY = "stacky.standup.lastShownDate";
const TARGET_HOUR = 9;
function todayKey() {
    return new Date().toISOString().slice(0, 10);
}
function shouldShow() {
    const now = new Date();
    if (now.getDay() === 0 || now.getDay() === 6)
        return false;
    if (now.getHours() < TARGET_HOUR)
        return false;
    return localStorage.getItem(SHOWN_KEY) !== todayKey();
}
export default function DailyStandupModal() {
    const [open, setOpen] = useState(false);
    const [data, setData] = useState(null);
    const [copied, setCopied] = useState(false);
    const tryShow = useCallback(() => {
        if (!shouldShow())
            return;
        api
            .get("/api/standup/daily")
            .then((d) => {
            setData(d);
            setOpen(true);
            localStorage.setItem(SHOWN_KEY, todayKey());
        })
            .catch(() => {
            // Silent: si el backend está caído, no molestar al usuario.
        });
    }, []);
    useEffect(() => {
        tryShow();
        const interval = window.setInterval(tryShow, 5 * 60 * 1000);
        return () => window.clearInterval(interval);
    }, [tryShow]);
    if (!open || !data)
        return null;
    const copyToClipboard = async () => {
        try {
            await navigator.clipboard.writeText(data.summary_text);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
        }
        catch {
            // ignore
        }
    };
    return (_jsx("div", { className: styles.backdrop, role: "dialog", "aria-modal": "true", "aria-label": "Standup diario", children: _jsxs("div", { className: styles.modal, children: [_jsxs("header", { className: styles.header, children: [_jsxs("h2", { className: styles.title, children: ["\u2600\uFE0F Buen d\u00EDa, ", data.user.split("@")[0], "."] }), _jsx("p", { className: styles.subtitle, children: "Tu standup est\u00E1 listo." })] }), _jsx("pre", { className: styles.content, children: data.summary_text }), _jsxs("footer", { className: styles.footer, children: [_jsx("button", { className: styles.primaryBtn, onClick: copyToClipboard, children: copied ? "✓ Copiado" : "Copiar para Teams" }), _jsx("button", { className: styles.secondaryBtn, onClick: () => setOpen(false), children: "Cerrar" })] })] }) }));
}
