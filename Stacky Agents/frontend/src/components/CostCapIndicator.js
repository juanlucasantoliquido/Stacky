import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./CostCapIndicator.module.css";
export default function CostCapIndicator({ projectName }) {
    const [data, setData] = useState(null);
    useEffect(() => {
        let cancelled = false;
        const refresh = () => {
            const url = projectName
                ? `/api/cost-cap?project=${encodeURIComponent(projectName)}`
                : "/api/cost-cap";
            api
                .get(url)
                .then((d) => {
                if (!cancelled)
                    setData(d);
            })
                .catch(() => {
                if (!cancelled)
                    setData(null);
            });
        };
        refresh();
        const t = window.setInterval(refresh, 60_000);
        return () => {
            cancelled = true;
            window.clearInterval(t);
        };
    }, [projectName]);
    if (!data || data.state === "unset")
        return null;
    const stateClass = data.state === "alert" ? styles.alert :
        data.state === "over" || data.state === "blocked" ? styles.over :
            styles.ok;
    const title = `Costo mensual: $${data.spent_usd.toFixed(2)} / $${data.monthly_cap_usd.toFixed(2)} (${data.spent_pct.toFixed(0)}%)`;
    return (_jsxs("span", { className: `${styles.chip} ${stateClass}`, title: title, children: [_jsx("span", { "aria-hidden": "true", children: "\uD83D\uDCB0" }), "$", data.spent_usd.toFixed(2), "/", data.monthly_cap_usd.toFixed(0), _jsx("span", { className: styles.bar, "aria-hidden": "true", children: _jsx("span", { className: styles.fill, style: { width: `${Math.min(100, data.spent_pct)}%` } }) })] }));
}
