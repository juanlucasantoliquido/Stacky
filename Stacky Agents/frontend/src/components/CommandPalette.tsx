import { useEffect, useMemo, useRef, useState } from "react";
import { Agents, GlobalSearchApi, Packs, Projects, Tickets } from "../api/endpoints";
// Plan 267 F5 [C21] — rawGet, NUNCA api.get: api.get delega en request<T>(), que
// hace `if (!res.ok) throw` en todo non-2xx, y el 404 NO es un caso raro acá: es
// el camino DOCUMENTADO de STACKY_DEVOPS_ACTION_CATALOG_ENABLED en OFF. Con
// api.get, cada apertura de la paleta con la flag apagada tiraría una promesa
// rechazada sin capturar. rawGet devuelve { status, ok, data } y solo lanza ante
// un fallo de red.
import { rawGet } from "../api/client";
import LoadErrorState from "./LoadErrorState";
import type { RemoteGroup } from "./commandPaletteData";
import {
  buildNavCommands,
  devopsActionCommands,
  fuzzyScore,
  mergeDeepResults,
} from "./commandPaletteData";
import type { Command } from "./commandPaletteData";
import { bindingFor } from "../services/devopsActionBindings";
import { runDevOpsAction } from "../services/devopsActionRunner";
import type { DevOpsActionMeta } from "../services/devopsActionTypes";
import { useConfirm } from "./ui";
import { useOnboardingStore } from "../store/onboardingStore";
// Plan 282 F4 — el rotulo del tab de tickets sigue al tracker del proyecto activo.
import { useWorkbench } from "../store/workbench";
import styles from "./CommandPalette.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
  onNavigate: (path: string) => void;
  /** Plan 129 — ADICIÓN ARQUITECTO: leído una vez en App.tsx (mismo patrón que
   *  migradorEnabled/devopsEnabled), no por apertura de paleta. */
  deepSearchEnabled?: boolean;
  /** Plan 238 — con la bandeja apagada, su entrada NO aparece en la paleta (P9). */
  incidentInboxEnabled?: boolean;
  /** Plan 172 F6 — los atajos se descubren donde el operador ya mira. */
  onOpenShortcuts?: () => void;
}

const DEEP_SEARCH_DEBOUNCE_MS = 250;
const DEEP_SEARCH_MIN_CHARS = 2;

export default function CommandPalette({ open, onClose, onNavigate, deepSearchEnabled = false, incidentInboxEnabled = false, onOpenShortcuts }: Props) {
  const [query, setQuery] = useState("");
  const [tickets, setTickets] = useState<{ id: number; ado_id: number; title: string }[]>([]);
  const [agents, setAgents] = useState<{ filename: string; name?: string }[]>([]);
  const [packs, setPacks] = useState<{ id: string; name: string }[]>([]);
  const [projects, setProjects] = useState<{ name: string }[]>([]);
  const [remoteGroups, setRemoteGroups] = useState<RemoteGroup[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [loadFailed, setLoadFailed] = useState<string[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  // Plan 267 F5 — acciones DevOps. Se piden UNA SOLA VEZ al abrir la paleta,
  // NUNCA en un intervalo (§4 principio 9: ninguna fase introduce sondeo).
  const [devopsActions, setDevopsActions] = useState<DevOpsActionMeta[]>([]);
  const askConfirm = useConfirm();
  // Plan 282 F4 — misma fuente que App.tsx y TicketBoard.
  const trackerType = useWorkbench((s) => s.activeProject?.tracker_type ?? null);

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
    // Plan 267 F5 [C21] — con la flag apagada el GET da 404 y rawGet NO lanza:
    // acciones = [] y la paleta queda EXACTAMENTE como hoy, sin banner y sin
    // error. Por eso este camino no suma nada a loadFailed.
    rawGet<{ ok: boolean; actions: DevOpsActionMeta[] }>("/devops/actions/catalog")
      .then((r) => setDevopsActions(r.ok && r.data ? r.data.actions ?? [] : []))
      .catch(() => setDevopsActions([]));
  }, [open, reloadKey]);

  useEffect(() => {
    if (!open || !deepSearchEnabled || query.trim().length < DEEP_SEARCH_MIN_CHARS) {
      setRemoteGroups([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      GlobalSearchApi.query(query, 8, controller.signal)
        .then((res) => setRemoteGroups(res.groups ?? []))
        .catch(() => setRemoteGroups([]));
    }, DEEP_SEARCH_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [open, deepSearchEnabled, query]);

  const allCommands: Command[] = useMemo(() => {
    const commands: Command[] = [];
    commands.push(
      // Plan 238 — la entrada de la bandeja se filtra con el mismo gate que el tab.
      ...buildNavCommands(trackerType).filter((nc) => nc.id !== "nav-incidencias" || incidentInboxEnabled).map((nc) => ({
        id: nc.id,
        kind: "nav" as const,
        icon: nc.icon,
        label: nc.label,
        run: () => onNavigate(nc.path),
      })),
    );
    // Plan 172 F6 — nadie descubre un atajo leyendo el código: el comando vive
    // donde el operador ya busca cosas.
    if (onOpenShortcuts) {
      commands.push({
        id: "action-shortcuts-overlay",
        kind: "nav" as const,
        icon: "⌨️",
        label: "Ver atajos de teclado",
        hint: "?",
        run: () => onOpenShortcuts(),
      });
    }
    // Plan 151 F4b: segundo punto de entrada al tour desde la paleta (reuso 129).
    commands.push({
      id: "nav-help-tour",
      kind: "nav" as const,
      icon: "❓",
      label: "Ver tour de bienvenida",
      run: () => useOnboardingStore.getState().requestOpenTour(),
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
    // Plan 267 F5 — las acciones DevOps van DESPUES de NAV_COMMANDS y del resto:
    // la paleta pasa de ser un ascensor a ser tambien un panel de mandos, sin
    // desplazar nada de lo que ya habia. paletteMode() garantiza que ninguna
    // ESCRITURA se ejecute desde aca: como maximo navega a su seccion.
    commands.push(
      ...devopsActionCommands(
        devopsActions,
        (a) => {
          void runDevOpsAction(a, {}, bindingFor(a.id), {
            askConfirm,
            navigate: onNavigate,
            now: () => Date.now(),
          });
        },
        onNavigate,
      ),
    );
    return commands;
  }, [tickets, agents, packs, projects, devopsActions, askConfirm, onNavigate, onOpenShortcuts, trackerType, incidentInboxEnabled]);

  const filtered = useMemo(() => {
    if (!query.trim()) {
      return allCommands.slice(0, 25);
    }
    const localMatches = allCommands
      .map((c) => ({ c, score: fuzzyScore(query, c.label) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .map((x) => x.c);
    const localIds = new Set(localMatches.map((c) => c.id));
    const deepMatches = mergeDeepResults(localIds, remoteGroups, onNavigate);
    return [...localMatches, ...deepMatches].slice(0, 40);
  }, [allCommands, query, remoteGroups, onNavigate]);

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
