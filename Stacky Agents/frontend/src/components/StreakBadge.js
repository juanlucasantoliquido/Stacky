import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./StreakBadge.module.css";
export default function StreakBadge() {
    const [data, setData] = useState(null);
    useEffect(() => {
        let cancelled = false;
        const refresh = () => {
            api
                .get("/api/streak")
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
        const t = window.setInterval(refresh, 5 * 60 * 1000);
        return () => {
            cancelled = true;
            window.clearInterval(t);
        };
    }, []);
    if (!data || data.current_streak <= 0)
        return null;
    const title = `${data.current_streak} días seguidos cerrando tickets con asistencia de agentes.\nMejor racha: ${data.best_streak}.`;
    return (_jsxs("span", { className: styles.badge, title: title, "aria-label": title, children: [_jsx("span", { "aria-hidden": "true", children: "\uD83D\uDD25" }), _jsx("span", { className: styles.count, children: data.current_streak })] }));
}
