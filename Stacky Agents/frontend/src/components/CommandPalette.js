import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useRef, useState } from "react";
import { Agents, Packs, Projects, Tickets } from "../api/endpoints";
import styles from "./CommandPalette.module.css";
function fuzzyScore(query, text) {
    if (!query)
        return 1;
    const q = query.toLowerCase();
    const t = text.toLowerCase();
    if (t.includes(q))
        return 100 - (t.indexOf(q));
    // Cada caracter de q debe aparecer en orden en t
    let qi = 0;
    let lastIdx = -1;
    let gaps = 0;
    for (let ti = 0; ti < t.length && qi < q.length; ti++) {
        if (t[ti] === q[qi]) {
            if (lastIdx >= 0)
                gaps += ti - lastIdx - 1;
            lastIdx = ti;
            qi++;
        }
    }
    if (qi < q.length)
        return 0;
    return Math.max(1, 50 - gaps);
}
export default function CommandPalette({ open, onClose, onNavigate }) {
    const [query, setQuery] = useState("");
    const [tickets, setTickets] = useState([]);
    const [agents, setAgents] = useState([]);
    const [packs, setPacks] = useState([]);
    const [projects, setProjects] = useState([]);
    const [selectedIdx, setSelectedIdx] = useState(0);
    const inputRef = useRef(null);
    useEffect(() => {
        if (!open)
            return;
        setQuery("");
        setSelectedIdx(0);
        inputRef.current?.focus();
        Tickets.list()
            .then((rows) => setTickets(rows.slice(0, 200).map((t) => ({
            id: t.id,
            ado_id: t.ado_id,
            title: t.title,
        }))))
            .catch(() => setTickets([]));
        Agents.vsCodeAgents()
            .then((rows) => setAgents(rows.map((a) => ({
            filename: a.filename,
            name: a.name,
        }))))
            .catch(() => setAgents([]));
        Packs.list?.()
            .then((rows) => setPacks((rows || []).map((p) => ({ id: p.id, name: p.name }))))
            .catch(() => setPacks([]));
        Projects.list?.()
            .then((res) => {
            const list = Array.isArray(res) ? res : res?.projects ?? [];
            setProjects(list.map((p) => ({ name: p.name })));
        })
            .catch(() => setProjects([]));
    }, [open]);
    const allCommands = useMemo(() => {
        const commands = [];
        commands.push({
            id: "nav-team",
            kind: "nav",
            icon: "⚡",
            label: "Ir a Mi Equipo",
            run: () => onNavigate("/"),
        }, {
            id: "nav-tickets",
            kind: "nav",
            icon: "📋",
            label: "Ir a Tickets ADO",
            run: () => onNavigate("/tickets"),
        }, {
            id: "nav-settings",
            kind: "nav",
            icon: "⚙️",
            label: "Ir a Configuración",
            run: () => onNavigate("/settings"),
        }, {
            id: "nav-diagnostics",
            kind: "nav",
            icon: "🩺",
            label: "Ir a Diagnóstico",
            run: () => onNavigate("/diagnostics"),
        }, {
            id: "nav-pm",
            kind: "nav",
            icon: "📊",
            label: "Ir a PM",
            run: () => onNavigate("/pm"),
        }, {
            id: "nav-logs",
            kind: "nav",
            icon: "🔍",
            label: "Ir a System Logs",
            run: () => onNavigate("/logs"),
        });
        for (const t of tickets) {
            commands.push({
                id: `ticket-${t.id}`,
                kind: "ticket",
                icon: "🎫",
                label: `T-${t.ado_id} — ${t.title}`,
                hint: "Abrir ticket",
                run: () => onNavigate(`/tickets?ticket=${t.id}`),
            });
        }
        for (const a of agents) {
            commands.push({
                id: `agent-${a.filename}`,
                kind: "agent",
                icon: "🤖",
                label: `Agente ${a.name ?? a.filename}`,
                run: () => onNavigate(`/?agent=${encodeURIComponent(a.filename)}`),
            });
        }
        for (const p of packs) {
            commands.push({
                id: `pack-${p.id}`,
                kind: "pack",
                icon: "📦",
                label: `Pack ${p.name}`,
                run: () => onNavigate(`/?pack=${encodeURIComponent(p.id)}`),
            });
        }
        for (const pr of projects) {
            commands.push({
                id: `project-${pr.name}`,
                kind: "project",
                icon: "📁",
                label: `Proyecto ${pr.name}`,
                run: () => onNavigate(`/?project=${encodeURIComponent(pr.name)}`),
            });
        }
        return commands;
    }, [tickets, agents, packs, projects, onNavigate]);
    const filtered = useMemo(() => {
        if (!query.trim()) {
            return allCommands.slice(0, 25);
        }
        return allCommands
            .map((c) => ({ c, score: fuzzyScore(query, c.label) }))
            .filter((x) => x.score > 0)
            .sort((a, b) => b.score - a.score)
            .slice(0, 40)
            .map((x) => x.c);
    }, [allCommands, query]);
    useEffect(() => {
        setSelectedIdx(0);
    }, [query]);
    if (!open)
        return null;
    const runSelected = () => {
        const cmd = filtered[selectedIdx];
        if (!cmd)
            return;
        cmd.run();
        onClose();
    };
    return (_jsx("div", { className: styles.backdrop, role: "dialog", "aria-modal": "true", onClick: (e) => {
            if (e.target === e.currentTarget)
                onClose();
        }, children: _jsxs("div", { className: styles.palette, children: [_jsxs("div", { className: styles.inputRow, children: [_jsx("span", { className: styles.searchIcon, "aria-hidden": "true", children: "\uD83D\uDD0D" }), _jsx("input", { ref: inputRef, className: styles.input, placeholder: "Buscar tickets, agentes, packs o ir a\u2026", value: query, onChange: (e) => setQuery(e.target.value), onKeyDown: (e) => {
                                if (e.key === "Escape") {
                                    e.preventDefault();
                                    onClose();
                                }
                                else if (e.key === "ArrowDown") {
                                    e.preventDefault();
                                    setSelectedIdx((i) => Math.min(filtered.length - 1, i + 1));
                                }
                                else if (e.key === "ArrowUp") {
                                    e.preventDefault();
                                    setSelectedIdx((i) => Math.max(0, i - 1));
                                }
                                else if (e.key === "Enter") {
                                    e.preventDefault();
                                    runSelected();
                                }
                            } })] }), _jsx("ul", { className: styles.list, role: "listbox", children: filtered.length === 0 ? (_jsx("li", { className: styles.empty, children: "Sin resultados" })) : (filtered.map((cmd, idx) => (_jsxs("li", { role: "option", "aria-selected": idx === selectedIdx, className: `${styles.item} ${idx === selectedIdx ? styles.selected : ""}`, onMouseEnter: () => setSelectedIdx(idx), onClick: () => {
                            cmd.run();
                            onClose();
                        }, children: [_jsx("span", { className: styles.itemIcon, children: cmd.icon }), _jsx("span", { className: styles.itemLabel, children: cmd.label }), cmd.hint ? _jsx("span", { className: styles.itemHint, children: cmd.hint }) : null] }, cmd.id)))) }), _jsxs("footer", { className: styles.footer, children: [_jsx("span", { children: "\u2191\u2193 navegar" }), _jsx("span", { children: "\u21B5 ejecutar" }), _jsx("span", { children: "Esc cerrar" })] })] }) }));
}
