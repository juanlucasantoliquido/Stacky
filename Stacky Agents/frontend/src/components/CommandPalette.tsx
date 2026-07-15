import { useEffect, useMemo, useRef, useState } from "react";
import { Agents, Packs, Projects, Tickets } from "../api/endpoints";
import LoadErrorState from "./LoadErrorState";
import styles from "./CommandPalette.module.css";

type CommandKind = "ticket" | "agent" | "pack" | "project" | "nav";

interface Command {
  id: string;
  kind: CommandKind;
  icon: string;
  label: string;
  hint?: string;
  run: () => void;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onNavigate: (path: string) => void;
}

function fuzzyScore(query: string, text: string): number {
  if (!query) return 1;
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  if (t.includes(q)) return 100 - (t.indexOf(q));
  // Cada caracter de q debe aparecer en orden en t
  let qi = 0;
  let lastIdx = -1;
  let gaps = 0;
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) {
      if (lastIdx >= 0) gaps += ti - lastIdx - 1;
      lastIdx = ti;
      qi++;
    }
  }
  if (qi < q.length) return 0;
  return Math.max(1, 50 - gaps);
}

export default function CommandPalette({ open, onClose, onNavigate }: Props) {
  const [query, setQuery] = useState("");
  const [tickets, setTickets] = useState<{ id: number; ado_id: number; title: string }[]>([]);
  const [agents, setAgents] = useState<{ filename: string; name?: string }[]>([]);
  const [packs, setPacks] = useState<{ id: string; name: string }[]>([]);
  const [projects, setProjects] = useState<{ name: string }[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [loadFailed, setLoadFailed] = useState<string[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSelectedIdx(0);
    setLoadFailed([]);
    inputRef.current?.focus();

    Tickets.list()
      .then((rows: any[]) =>
        setTickets(rows.slice(0, 200).map((t) => ({
          id: t.id,
          ado_id: t.ado_id,
          title: t.title,
        })))
      )
      .catch(() => { setTickets([]); setLoadFailed((p) => [...p, "tickets"]); });
    Agents.vsCodeAgents()
      .then((rows: any[]) => setAgents(rows.map((a) => ({
        filename: a.filename,
        name: a.name,
      }))))
      .catch(() => { setAgents([]); setLoadFailed((p) => [...p, "agentes"]); });
    Packs.list?.()
      .then((rows: any[]) => setPacks((rows || []).map((p) => ({ id: p.id, name: p.name }))))
      .catch(() => { setPacks([]); setLoadFailed((p) => [...p, "packs"]); });
    Projects.list?.()
      .then((res: any) => {
        const list = Array.isArray(res) ? res : res?.projects ?? [];
        setProjects(list.map((p: any) => ({ name: p.name })));
      })
      .catch(() => { setProjects([]); setLoadFailed((p) => [...p, "proyectos"]); });
  }, [open, reloadKey]);

  const allCommands: Command[] = useMemo(() => {
    const commands: Command[] = [];
    commands.push(
      {
        id: "nav-team",
        kind: "nav",
        icon: "⚡",
        label: "Ir a Mi Equipo",
        run: () => onNavigate("/"),
      },
      {
        id: "nav-tickets",
        kind: "nav",
        icon: "📋",
        label: "Ir a Tickets ADO",
        run: () => onNavigate("/tickets"),
      },
      {
        id: "nav-settings",
        kind: "nav",
        icon: "⚙️",
        label: "Ir a Configuración",
        run: () => onNavigate("/settings"),
      },
      {
        id: "nav-diagnostics",
        kind: "nav",
        icon: "🩺",
        label: "Ir a Diagnóstico",
        run: () => onNavigate("/diagnostics"),
      },
      {
        id: "nav-pm",
        kind: "nav",
        icon: "📊",
        label: "Ir a PM",
        run: () => onNavigate("/pm"),
      },
      {
        id: "nav-logs",
        kind: "nav",
        icon: "🔍",
        label: "Ir a System Logs",
        run: () => onNavigate("/logs"),
      },
    );
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

  if (!open) return null;

  const runSelected = () => {
    const cmd = filtered[selectedIdx];
    if (!cmd) return;
    cmd.run();
    onClose();
  };

  return (
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={styles.palette}>
        <div className={styles.inputRow}>
          <span className={styles.searchIcon} aria-hidden="true">🔍</span>
          <input
            ref={inputRef}
            className={styles.input}
            placeholder="Buscar tickets, agentes, packs o ir a…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                onClose();
              } else if (e.key === "ArrowDown") {
                e.preventDefault();
                setSelectedIdx((i) => Math.min(filtered.length - 1, i + 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setSelectedIdx((i) => Math.max(0, i - 1));
              } else if (e.key === "Enter") {
                e.preventDefault();
                runSelected();
              }
            }}
          />
        </div>
        {loadFailed.length > 0 && (
          <LoadErrorState
            compact
            what={loadFailed.join(", ")}
            onRetry={() => setReloadKey((k) => k + 1)}
          />
        )}
        <ul className={styles.list} role="listbox">
          {filtered.length === 0 ? (
            <li className={styles.empty}>Sin resultados</li>
          ) : (
            filtered.map((cmd, idx) => (
              <li
                key={cmd.id}
                role="option"
                aria-selected={idx === selectedIdx}
                className={`${styles.item} ${idx === selectedIdx ? styles.selected : ""}`}
                onMouseEnter={() => setSelectedIdx(idx)}
                onClick={() => {
                  cmd.run();
                  onClose();
                }}
              >
                <span className={styles.itemIcon}>{cmd.icon}</span>
                <span className={styles.itemLabel}>{cmd.label}</span>
                {cmd.hint ? <span className={styles.itemHint}>{cmd.hint}</span> : null}
              </li>
            ))
          )}
        </ul>
        <footer className={styles.footer}>
          <span>↑↓ navegar</span>
          <span>↵ ejecutar</span>
          <span>Esc cerrar</span>
        </footer>
      </div>
    </div>
  );
}
