import React, { useState, useEffect, useCallback, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Agents, Executions, Tickets, Projects, type TicketAttachment, type AgentHistoryEntry } from "../api/endpoints";
import type { AgentExecution } from "../types";
import { useWorkbench } from "../store/workbench";
import PixelAvatar from "./PixelAvatar";
import styles from "./AgentHistoryPage.module.css";

/*
 * P2.3 — AgentHistoryPage
 * Portado de WS2 (N:\SVN\RS\Agentes\Stacky Agents\frontend\src\components\AgentHistoryPage.tsx).
 *
 * Adaptaciones WS1:
 *  - Usa Executions.list con agent_filename (agregado en endpoints.ts).
 *  - Agents.history recibe project_name opcional (agregado en endpoints.ts).
 *  - TicketAttachment, Executions.deleteOne/deleteByTicket/forceTransition/reattach
 *    agregados a endpoints.ts en este mismo sprint.
 *  - api.delete ahora acepta body (agregado en client.ts).
 */

interface AgentHistoryPageProps {
  filename: string;
  displayName: string;
  avatarValue: string | null;
  onBack: () => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────

const AGENT_TYPE_BADGE: Record<string, { color: string; bg: string; label: string }> = {
  business:   { color: "#a371f7", bg: "rgba(163,113,247,0.18)", label: "Business"   },
  functional: { color: "#f78166", bg: "rgba(247,129,102,0.18)", label: "Functional" },
  technical:  { color: "#388bfd", bg: "rgba(56,139,253,0.18)",  label: "Technical"  },
  developer:  { color: "#3fb950", bg: "rgba(63,185,80,0.18)",   label: "Developer"  },
  qa:         { color: "#d29922", bg: "rgba(210,153,34,0.18)",  label: "QA"         },
  custom:     { color: "#8b949e", bg: "rgba(139,148,158,0.18)", label: "Custom"     },
};

function inferAgentType(filename: string): string {
  const f = filename.toLowerCase();
  if (f.includes("business") || f.includes("negocio")) return "business";
  if (f.includes("functional") || f.includes("funcional")) return "functional";
  if (f.includes("technical") || f.includes("tecnic")) return "technical";
  if (f.includes("dev") || f.includes("desarrollador")) return "developer";
  if (f.includes("qa") || f.includes("test")) return "qa";
  return "custom";
}

function agentBadgeInfo(agentLabel: string): { style: React.CSSProperties; label: string } {
  const type = inferAgentType(agentLabel);
  const spec = AGENT_TYPE_BADGE[type] ?? AGENT_TYPE_BADGE.custom;
  return { style: { color: spec.color, backgroundColor: spec.bg }, label: spec.label };
}

function agentForFile(name: string, map: Record<string, string>): string | null {
  const upper = name.toUpperCase();
  for (const [prefix, agent] of Object.entries(map)) {
    if (upper.startsWith(prefix.toUpperCase())) return agent;
  }
  return null;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" })
    + " " + d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
}

function fmtDuration(ms: number | null | undefined): string {
  if (!ms) return "";
  if (ms < 1000) return `${ms}ms`;
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    completed: "Completado",
    published: "Publicado",
    cancelled: "Cancelado",
    error: "Error",
    running: "En curso",
    pending: "Pendiente",
    vscode_chat: "VS Code Chat",
  };
  return map[s] ?? s;
}

function triggerDownload(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// ── File viewer / editor ───────────────────────────────────────────────────

interface FileDetailProps {
  ticketId: number;
  att: TicketAttachment;
  mode: "view" | "edit";
  onClose: () => void;
  onDeleted: () => void;
}

function FileDetail({ ticketId, att, mode: initialMode, onClose, onDeleted }: FileDetailProps) {
  const [content, setContent] = useState<string>("");
  const [editContent, setEditContent] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"view" | "edit">(initialMode);
  const [rawView, setRawView] = useState(false);
  const ext = att.name.split(".").pop()?.toLowerCase() ?? "";
  const isMarkdown = ext === "md";
  const CODE_LANG: Record<string, string> = { sql: "sql", diff: "diff", patch: "diff" };
  const codeLang = CODE_LANG[ext] ?? "";
  const isRenderable = isMarkdown || !!codeLang;

  useEffect(() => {
    setLoading(true);
    setError(null);
    Tickets.attachmentContent(ticketId, att.url, att.name)
      .then((r) => {
        if (r.ok && r.content != null) {
          setContent(r.content);
          setEditContent(r.content);
        } else {
          setError(r.error ?? "No se pudo cargar el contenido");
        }
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [ticketId, att.url, att.name]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      await Tickets.deleteAttachments(ticketId, [{ id: att.id, url: att.url, name: att.name }]);
      const res = await Tickets.uploadAttachment(ticketId, att.name, editContent);
      if (!res.ok) {
        setError(res.error ?? "Error al guardar");
        return;
      }
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }, [ticketId, att, editContent, onClose]);

  void onDeleted; // satisface el linter -- se propaga via onClose en el flujo de borrado del padre

  return (
    <div className={styles.fileDetail}>
      <div className={styles.fileDetailHeader}>
        <span className={styles.fileDetailName}>{att.name}</span>
        <div className={styles.fileDetailActions}>
          {mode === "view" && !loading && !error && (
            <>
              {isRenderable && (
                <button className={styles.btnIcon} title={rawView ? "Ver renderizado" : "Ver raw"} onClick={() => setRawView((v) => !v)}>
                  {rawView ? "Render" : "</>"}
                </button>
              )}
              <button className={styles.btnIcon} title="Editar" onClick={() => setMode("edit")}>Editar</button>
              <button className={styles.btnIcon} title="Descargar" onClick={() => triggerDownload(att.name, content)}>Descargar</button>
            </>
          )}
          {mode === "edit" && (
            <button
              className={styles.btnPrimary}
              onClick={handleSave}
              disabled={saving || loading}
            >
              {saving ? "Guardando..." : "Guardar"}
            </button>
          )}
          <button className={styles.btnClose} onClick={onClose}>X</button>
        </div>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      {loading ? (
        <div className={styles.loading}>Cargando...</div>
      ) : mode === "view" ? (
        isMarkdown && !rawView ? (
          <div className={styles.fileMarkdown}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>{content}</ReactMarkdown>
          </div>
        ) : codeLang && !rawView ? (
          <div className={styles.fileMarkdown}>
            <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{`\`\`\`${codeLang}\n${content}\n\`\`\``}</ReactMarkdown>
          </div>
        ) : (
          <pre className={styles.fileContent}>{content}</pre>
        )
      ) : (
        <textarea
          className={styles.fileEditor}
          value={editContent}
          onChange={(e) => setEditContent(e.target.value)}
          spellCheck={false}
          disabled={saving}
        />
      )}
    </div>
  );
}

// ── Files tab ─────────────────────────────────────────────────────────────

interface FilesTabProps {
  ticketId: number;
  prefixAgentMap?: Record<string, string>;
}

function FilesTab({ ticketId, prefixAgentMap = {} }: FilesTabProps) {
  const [attachments, setAttachments] = useState<TicketAttachment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ att: TicketAttachment; mode: "view" | "edit" } | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Tickets.attachments(ticketId)
      .then((r) => {
        setAttachments(r.attachments ?? []);
        if (r.error) setError(r.error);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [ticketId]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = useCallback(async (att: TicketAttachment) => {
    if (!confirm(`Eliminar "${att.name}"?`)) return;
    setDeleting(att.id);
    try {
      await Tickets.deleteAttachments(ticketId, [{ id: att.id, url: att.url, name: att.name }]);
      setAttachments((prev) => prev.filter((a) => a.id !== att.id));
      if (detail?.att.id === att.id) setDetail(null);
    } catch (e) {
      alert(String(e));
    } finally {
      setDeleting(null);
    }
  }, [ticketId, detail]);

  const handleDownload = useCallback(async (att: TicketAttachment) => {
    setDownloadingId(att.id);
    try {
      const r = await Tickets.attachmentContent(ticketId, att.url, att.name);
      if (r.ok && r.content != null) {
        triggerDownload(att.name, r.content);
      } else {
        alert(r.error ?? "No se pudo descargar");
      }
    } catch (e) {
      alert(String(e));
    } finally {
      setDownloadingId(null);
    }
  }, [ticketId]);

  if (loading) return <div className={styles.loading}>Cargando ficheros...</div>;
  if (error) return <div className={styles.error}>{error}</div>;

  if (detail) {
    return (
      <FileDetail
        ticketId={ticketId}
        att={detail.att}
        mode={detail.mode}
        onClose={() => { setDetail(null); load(); }}
        onDeleted={() => { setDetail(null); load(); }}
      />
    );
  }

  if (!attachments.length) {
    return (
      <div className={styles.empty}>No hay ficheros adjuntos en este ticket.</div>
    );
  }

  return (
    <div className={styles.fileList}>
      {attachments.map((att) => {
        const agentLabel = agentForFile(att.name, prefixAgentMap);
        const badgeInfo = agentLabel ? agentBadgeInfo(agentLabel) : null;
        return (
          <div key={att.id} className={styles.fileRow}>
            <span className={styles.fileIcon}>F</span>
            <span className={styles.fileName}>{att.name}</span>
            {badgeInfo && (
              <span
                className={styles.agentBadge}
                style={badgeInfo.style}
                title={`Generado por: ${agentLabel}`}
              >
                {badgeInfo.label}
              </span>
            )}
            {att.size > 0 && (
              <span className={styles.fileSize}>
                {att.size < 1024 ? `${att.size}B` : `${(att.size / 1024).toFixed(1)}KB`}
              </span>
            )}
            <div className={styles.fileRowActions}>
              <button
                className={styles.btnIcon}
                title="Ver"
                onClick={() => setDetail({ att, mode: "view" })}
              >Ver</button>
              <button
                className={styles.btnIcon}
                title="Descargar"
                onClick={() => handleDownload(att)}
                disabled={downloadingId === att.id}
              >{downloadingId === att.id ? "..." : "Bajar"}</button>
              <button
                className={styles.btnIcon}
                title="Editar"
                onClick={() => setDetail({ att, mode: "edit" })}
              >Ed.</button>
              <button
                className={`${styles.btnIcon} ${styles.btnDanger}`}
                title="Eliminar"
                onClick={() => handleDelete(att)}
                disabled={deleting === att.id}
              >{deleting === att.id ? "..." : "Elim."}</button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Notes tab ─────────────────────────────────────────────────────────────

interface NotesTabProps {
  ticketId: number;
  agentFilename: string;
  onAllDeleted?: () => void;
}

function NotesTab({ ticketId, agentFilename, onAllDeleted }: NotesTabProps) {
  const [executions, setExecutions] = useState<AgentExecution[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [deleting, setDeleting] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Executions.list({
      ticket_id: ticketId,
      agent_filename: agentFilename,
      include_output: true,
      limit: 100,
    })
      .then(setExecutions)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [ticketId, agentFilename]);

  const toggle = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const handleDeleteNote = useCallback(async (ex: AgentExecution) => {
    if (!confirm(`Eliminar esta ejecucion (#${ex.id})?`)) return;
    setDeleting(ex.id);
    try {
      await Executions.deleteOne(ex.id);
      const remaining = executions.filter((e) => e.id !== ex.id);
      setExecutions(remaining);
      if (remaining.length === 0) onAllDeleted?.();
    } catch (e) {
      alert(String(e));
    } finally {
      setDeleting(null);
    }
  }, [executions, onAllDeleted]);

  if (loading) return <div className={styles.loading}>Cargando notas...</div>;
  if (error) return <div className={styles.error}>{error}</div>;
  if (!executions.length) return <div className={styles.empty}>No hay ejecuciones registradas para este ticket.</div>;

  return (
    <div className={styles.notesList}>
      {executions.map((ex) => {
        const isExpanded = expanded.has(ex.id);
        const hasOutput = !!ex.output?.trim();
        const isDeletable = !["running", "queued", "vscode_chat"].includes(ex.status);
        return (
          <div key={ex.id} className={styles.noteCard}>
            <div
              className={styles.noteHeader}
              onClick={() => hasOutput && toggle(ex.id)}
              style={{ cursor: hasOutput ? "pointer" : "default" }}
            >
              <span className={`${styles.statusBadge} ${styles[`status_${ex.status}` as keyof typeof styles] ?? ""}`}>
                {statusLabel(ex.status)}
              </span>
              <span className={styles.noteDate}>{fmtDate(ex.started_at)}</span>
              {ex.duration_ms != null && (
                <span className={styles.noteDuration}>{fmtDuration(ex.duration_ms)}</span>
              )}
              {ex.agent_filename && (
                <span className={styles.noteAgent}>{ex.agent_filename}</span>
              )}
              {hasOutput && (
                <span className={styles.noteToggle}>{isExpanded ? "v" : ">"}</span>
              )}
              {isDeletable && (
                <button
                  className={`${styles.btnIcon} ${styles.btnDanger}`}
                  title="Eliminar esta nota"
                  onClick={(e) => { e.stopPropagation(); handleDeleteNote(ex); }}
                  disabled={deleting === ex.id}
                  style={{ marginLeft: "auto" }}
                >
                  {deleting === ex.id ? "..." : "Elim."}
                </button>
              )}
            </div>
            {isExpanded && hasOutput && (
              <div className={styles.noteOutput}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{ex.output!}</ReactMarkdown>
              </div>
            )}
            {ex.error_message && (
              <div className={styles.noteError}>{ex.error_message}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function AgentHistoryPage({
  filename,
  displayName,
  avatarValue,
  onBack,
}: AgentHistoryPageProps) {
  const [tickets, setTickets] = useState<AgentHistoryEntry[]>([]);
  const [loadingTickets, setLoadingTickets] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<"notes" | "files">("notes");
  const [workflow, setWorkflow] = useState<{ allowed_states: string[]; transition_state: string } | null>(null);
  const [forcing, setForcing] = useState(false);
  const [forceResult, setForceResult] = useState<string | null>(null);
  const [reattaching, setReattaching] = useState(false);
  const [reattachResult, setReattachResult] = useState<string | null>(null);
  const [deletingTicketId, setDeletingTicketId] = useState<number | null>(null);

  const activeProject = useWorkbench((s) => s.activeProject);
  const agentWorkflows = useWorkbench((s) => s.agentWorkflows);
  const setAgentWorkflows = useWorkbench((s) => s.setAgentWorkflows);

  const prefixAgentMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const [fn, wf] of Object.entries(agentWorkflows)) {
      if (!(wf as { output_file_prefix?: string }).output_file_prefix) continue;
      const label = fn.replace(/\.agent\.md$/i, "").replace(/\.md$/i, "");
      for (const raw of ((wf as { output_file_prefix?: string }).output_file_prefix ?? "").split(",")) {
        const p = raw.trim();
        if (p) map[p] = label;
      }
    }
    return map;
  }, [agentWorkflows]);

  // Cargar TODOS los workflows del proyecto para poder mapear ficheros => agente
  useEffect(() => {
    if (!activeProject?.name) return;
    Projects.getAllAgentWorkflows(activeProject.name)
      .then((r) => {
        if (r.ok && r.workflows) {
          setAgentWorkflows({ ...agentWorkflows, ...r.workflows });
        }
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.name]);

  // Cargar lista de tickets
  useEffect(() => {
    setLoadingTickets(true);
    Agents.history(filename, 100, activeProject?.name)
      .then((r) => {
        setTickets(r.tickets ?? []);
        if (r.tickets?.length) setSelectedId(r.tickets[0].ticket_id);
      })
      .catch(() => setTickets([]))
      .finally(() => setLoadingTickets(false));
  }, [filename, activeProject?.name]);

  // Cargar workflow config para force-transition
  useEffect(() => {
    const wf = agentWorkflows[filename];
    if (wf) {
      setWorkflow({ allowed_states: wf.allowed_states ?? [], transition_state: wf.transition_state ?? "" });
      return;
    }
    if (activeProject?.name) {
      Projects.getAgentWorkflow(activeProject.name, filename)
        .then((r) => {
          if (r.ok) setWorkflow({ allowed_states: r.allowed_states ?? [], transition_state: r.transition_state ?? "" });
        })
        .catch(() => {});
    }
  }, [filename, agentWorkflows, activeProject]);

  const selectedTicket = tickets.find((t) => t.ticket_id === selectedId) ?? null;

  const filteredTickets = tickets.filter((t) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    return t.title.toLowerCase().includes(q) || String(t.ado_id).includes(q);
  });

  const canForce = !!(
    workflow &&
    selectedTicket?.ado_state &&
    workflow.allowed_states.includes(selectedTicket.ado_state) &&
    selectedTicket.executions_count > 0 &&
    selectedTicket.last_execution_status === "completed"
  );

  async function handleForce() {
    if (!selectedTicket) return;
    setForcing(true);
    setForceResult(null);
    try {
      const res = await Executions.forceTransition(selectedTicket.last_execution_id);
      setForceResult(res.ok ? `Transicionado a '${workflow?.transition_state}'` : (res.error ?? "Error al forzar transicion"));
    } catch (e: unknown) {
      setForceResult(String(e instanceof Error ? e.message : e));
    } finally {
      setForcing(false);
    }
  }

  async function handleReattach() {
    if (!selectedTicket) return;
    setReattaching(true);
    setReattachResult(null);
    try {
      const res = await Executions.reattach(selectedTicket.last_execution_id);
      setReattachResult(res.ok
        ? `Ficheros re-subidos (${res.tracker ?? ""} · prefijo: ${res.out_prefix ?? ""})`
        : (res.error ?? "Error al re-subir ficheros"));
    } catch (e: unknown) {
      setReattachResult(String(e instanceof Error ? e.message : e));
    } finally {
      setReattaching(false);
    }
  }

  async function handleDeleteTicket(t: AgentHistoryEntry, e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm(`Eliminar TODO el historial del ticket #${t.ado_id} "${t.title}"?\n\nSe borraran ${t.executions_count} ejecucion(es). Esta accion no se puede deshacer.`)) return;
    setDeletingTicketId(t.ticket_id);
    try {
      await Executions.deleteByTicket(t.ticket_id, filename);
      const remaining = tickets.filter((tk) => tk.ticket_id !== t.ticket_id);
      setTickets(remaining);
      if (selectedId === t.ticket_id) {
        setSelectedId(remaining.length > 0 ? remaining[0].ticket_id : null);
      }
    } catch (err: unknown) {
      alert(String(err instanceof Error ? err.message : err));
    } finally {
      setDeletingTicketId(null);
    }
  }

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>Volver</button>
        <div className={styles.agentInfo}>
          <PixelAvatar value={avatarValue} size="sm" name={displayName} />
          <span className={styles.agentName}>{displayName}</span>
        </div>
        <span className={styles.pageTitle}>Historial de ejecuciones</span>
      </div>

      <div className={styles.body}>
        {/* Sidebar: lista de tickets */}
        <aside className={styles.sidebar}>
          <div className={styles.sidebarTitle}>
            Tickets trabajados{activeProject ? ` · ${activeProject.display_name || activeProject.name}` : ""}
          </div>
          <div className={styles.sidebarSearch}>
            <input
              className={styles.sidebarSearchInput}
              type="search"
              placeholder="Buscar por titulo o ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {loadingTickets ? (
            <div className={styles.loading}>Cargando...</div>
          ) : filteredTickets.length === 0 ? (
            <div className={styles.sidebarEmpty}>
              {tickets.length === 0 ? "Sin historial" : "Sin resultados"}
            </div>
          ) : (
            <ul className={styles.ticketList}>
              {filteredTickets.map((t) => (
                <li
                  key={t.ticket_id}
                  className={`${styles.ticketItem} ${selectedId === t.ticket_id ? styles.ticketItemActive : ""}`}
                  onClick={() => { setSelectedId(t.ticket_id); setTab("notes"); setForceResult(null); setReattachResult(null); }}
                >
                  <div className={styles.ticketItemId}>#{t.ado_id}</div>
                  <div className={styles.ticketItemTitle}>{t.title}</div>
                  <div className={styles.ticketItemMeta}>
                    <span className={styles.ticketItemCount}>{t.executions_count} ej.</span>
                    {t.ado_state && (
                      <span className={styles.ticketItemState}>{t.ado_state}</span>
                    )}
                    <button
                      className={`${styles.btnIcon} ${styles.btnDanger} ${styles.ticketDeleteBtn}`}
                      title="Eliminar historial completo de este ticket"
                      onClick={(e) => handleDeleteTicket(t, e)}
                      disabled={deletingTicketId === t.ticket_id}
                    >
                      {deletingTicketId === t.ticket_id ? "..." : "Elim."}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>

        {/* Panel de detalle */}
        <main className={styles.detail}>
          {!selectedTicket ? (
            <div className={styles.noSelection}>Selecciona un ticket para ver su historial.</div>
          ) : (
            <>
              <div className={styles.detailHeader}>
                <div className={styles.detailTitle}>
                  <span className={styles.detailId}>#{selectedTicket.ado_id}</span>
                  {selectedTicket.title}
                </div>
                {selectedTicket.ado_url && (
                  <a
                    href={selectedTicket.ado_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.detailLink}
                  >Abrir</a>
                )}
                {canForce && (
                  <button
                    className={styles.forceTransBtn}
                    onClick={handleForce}
                    disabled={forcing}
                    title={`Transicionar a '${workflow?.transition_state}'`}
                  >
                    {forcing ? "..." : `=> ${workflow?.transition_state}`}
                  </button>
                )}
                {forceResult && (
                  <span className={`${styles.forceResult} ${forceResult.startsWith("Transicion") ? styles.forceOk : styles.forceErr}`}>
                    {forceResult}
                  </span>
                )}
                {selectedTicket.last_execution_status === "completed" && (
                  <button
                    className={styles.forceTransBtn}
                    onClick={handleReattach}
                    disabled={reattaching}
                    title="Re-intentar subir los ficheros generados al tracker"
                  >
                    {reattaching ? "..." : "Re-subir ficheros"}
                  </button>
                )}
                {reattachResult && (
                  <span className={`${styles.forceResult} ${reattachResult.startsWith("Ficheros") ? styles.forceOk : styles.forceErr}`}>
                    {reattachResult}
                  </span>
                )}
              </div>

              {/* Tabs */}
              <div className={styles.tabs}>
                <button
                  className={`${styles.tab} ${tab === "notes" ? styles.tabActive : ""}`}
                  onClick={() => setTab("notes")}
                >
                  Notas
                </button>
                <button
                  className={`${styles.tab} ${tab === "files" ? styles.tabActive : ""}`}
                  onClick={() => setTab("files")}
                >
                  Ficheros
                </button>
              </div>

              {/* Contenido del tab */}
              <div className={styles.tabContent}>
                {tab === "notes" && (
                  <NotesTab
                    key={selectedTicket.ticket_id}
                    ticketId={selectedTicket.ticket_id}
                    agentFilename={filename}
                    onAllDeleted={() => {
                      const remaining = tickets.filter((tk) => tk.ticket_id !== selectedTicket.ticket_id);
                      setTickets(remaining);
                      setSelectedId(remaining.length > 0 ? remaining[0].ticket_id : null);
                    }}
                  />
                )}
                {tab === "files" && (
                  <FilesTab
                    key={selectedTicket.ticket_id}
                    ticketId={selectedTicket.ticket_id}
                    prefixAgentMap={prefixAgentMap}
                  />
                )}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
