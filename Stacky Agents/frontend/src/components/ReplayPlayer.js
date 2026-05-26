import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import styles from "./ReplayPlayer.module.css";
const SPEEDS = [0.5, 1, 2, 4];
export default function ReplayPlayer({ executionId, open, onClose }) {
    const [events, setEvents] = useState([]);
    const [cursorMs, setCursorMs] = useState(0);
    const [playing, setPlaying] = useState(false);
    const [speed, setSpeed] = useState(1);
    const rafRef = useRef(null);
    const lastTickRef = useRef(null);
    useEffect(() => {
        if (!open || executionId == null)
            return;
        setCursorMs(0);
        setPlaying(false);
        api
            .get(`/api/executions/${executionId}/events`)
            .then((d) => setEvents(d.events))
            .catch(() => setEvents([]));
    }, [open, executionId]);
    const totalMs = events.length > 0
        ? (events[events.length - 1].t_relative_ms ?? 0)
        : 0;
    useEffect(() => {
        if (!playing) {
            if (rafRef.current !== null)
                cancelAnimationFrame(rafRef.current);
            lastTickRef.current = null;
            return;
        }
        const tick = (now) => {
            if (lastTickRef.current === null)
                lastTickRef.current = now;
            const dt = now - lastTickRef.current;
            lastTickRef.current = now;
            setCursorMs((c) => {
                const next = c + dt * speed;
                if (next >= totalMs) {
                    setPlaying(false);
                    return totalMs;
                }
                return next;
            });
            rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
        return () => {
            if (rafRef.current !== null)
                cancelAnimationFrame(rafRef.current);
        };
    }, [playing, speed, totalMs]);
    if (!open)
        return null;
    const shown = events.filter((e) => (e.t_relative_ms ?? 0) <= cursorMs);
    const progress = totalMs > 0 ? Math.min(100, (cursorMs / totalMs) * 100) : 0;
    return (_jsx("div", { className: styles.backdrop, onClick: (e) => {
            if (e.target === e.currentTarget)
                onClose();
        }, children: _jsxs("div", { className: styles.modal, children: [_jsxs("header", { className: styles.header, children: [_jsxs("h3", { children: ["\u25B6 Replay \u2014 Execution #", executionId] }), _jsx("button", { className: styles.closeBtn, onClick: onClose, "aria-label": "Cerrar", children: "\u00D7" })] }), _jsxs("div", { className: styles.controls, children: [_jsx("button", { className: styles.btn, onClick: () => setPlaying((p) => !p), disabled: events.length === 0, children: playing ? "⏸" : "▶" }), _jsx("button", { className: styles.btn, onClick: () => {
                                setCursorMs(0);
                                setPlaying(false);
                            }, children: "\u23EE" }), SPEEDS.map((s) => (_jsxs("button", { className: `${styles.btn} ${speed === s ? styles.active : ""}`, onClick: () => setSpeed(s), children: [s, "\u00D7"] }, s))), _jsxs("span", { className: styles.time, children: [(cursorMs / 1000).toFixed(1), "s / ", (totalMs / 1000).toFixed(1), "s"] })] }), _jsx("div", { className: styles.progressBar, children: _jsx("div", { className: styles.progressFill, style: { width: `${progress}%` } }) }), _jsx("ul", { className: styles.log, children: events.length === 0 ? (_jsx("li", { className: styles.empty, children: "Esta ejecuci\u00F3n no tiene timeline de eventos registrado." })) : (shown.map((ev, idx) => (_jsxs("li", { className: styles.event, children: [_jsxs("span", { className: styles.eventTime, children: ["[", ((ev.t_relative_ms ?? 0) / 1000).toFixed(2), "s]"] }), _jsx("span", { className: styles.eventKind, children: ev.kind }), ev.payload && Object.keys(ev.payload).length > 0 && (_jsx("span", { className: styles.eventPayload, children: JSON.stringify(ev.payload).slice(0, 140) }))] }, idx)))) })] }) }));
}
