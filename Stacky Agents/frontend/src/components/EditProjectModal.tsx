import React, { useState, useEffect } from "react";
import { Projects, Mantis, type MantisProject, type MantisListParams } from "../api/endpoints";
import type { AgentWorkflowConfig, InitProjectPayload, Project, TrackerType } from "../types";
import styles from "./NewProjectModal.module.css";

interface Props {
  project: Project;
  onClose: () => void;
  onSaved: () => void;
  onDelete: () => void;
}

export default function EditProjectModal({ project, onClose, onSaved, onDelete }: Props) {
  const [form, setForm] = useState<Partial<InitProjectPayload>>({
    display_name:         project.display_name,
    workspace_root:       project.workspace_root,
    tracker_type:         project.tracker_type,
    organization:         project.organization ?? "",
    ado_project:          project.ado_project ?? "",
    pat:                  "",
    jira_url:             project.jira_url ?? "",
    jira_key:             project.jira_key ?? "",
    api_version:          "3",
    jql:                  "",
    verify_ssl:           true,
    jira_user:            "",
    jira_token:           "",
    mantis_url:           project.mantis_url ?? "",
    mantis_project_id:    project.mantis_project_id ?? "",
    mantis_project_name:  project.mantis_project_name ?? "",
    mantis_protocol:      (project.mantis_protocol ?? "rest") as "rest" | "soap",
    mantis_token:         "",
    mantis_username:      "",
    mantis_password:      "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedUser, setLoadedUser] = useState<string | null>(null);

  // Mantis: listar proyectos disponibles
  const [mantisProjects, setMantisProjects] = useState<MantisProject[]>([]);
  const [mantisLoading, setMantisLoading] = useState(false);
  const [mantisLoadError, setMantisLoadError] = useState<string | null>(null);

  // Workflow por agente
  const [pinnedAgents, setPinnedAgents] = useState<string[]>([]);
  const [trackerStates, setTrackerStates] = useState<string[]>([]);
  const [workflows, setWorkflows] = useState<Record<string, AgentWorkflowConfig>>({});
  const [savingWorkflow, setSavingWorkflow] = useState<string | null>(null);

  // Carga el usuario guardado para mostrarlo en el placeholder
  useEffect(() => {
    Projects.getCredentials(project.name)
      .then((res) => {
        if (res.ok) {
          if (res.jira_user) {
            setLoadedUser(res.jira_user);
            setForm((f) => ({ ...f, jira_user: res.jira_user ?? "" }));
          }
          // Para Mantis: si hay project_id y protocol guardado en auth, los usamos
          if (res.mantis_project_id) {
            setForm((f) => ({ ...f, mantis_project_id: res.mantis_project_id ?? "" }));
          }
          if (res.mantis_protocol) {
            setForm((f) => ({ ...f, mantis_protocol: (res.mantis_protocol ?? "rest") as "rest" | "soap" }));
          }
        }
      })
      .catch(() => {});

    // Cargar agentes fijados
    Projects.getAgents(project.name)
      .then((res) => { if (res.ok) setPinnedAgents(res.pinned_agents ?? []); })
      .catch(() => {});

    // Cargar estados del tracker
    Projects.trackerStates(project.name)
      .then((res) => { if (res.ok) setTrackerStates(res.states ?? []); })
      .catch(() => {});
  }, [project.name]);

  // Cargar workflow de cada agente fijado
  useEffect(() => {
    if (pinnedAgents.length === 0) return;
    pinnedAgents.forEach((filename) => {
      Projects.getAgentWorkflow(project.name, filename)
        .then((res) => {
          if (res.ok) {
            setWorkflows((prev) => ({
              ...prev,
              [filename]: {
                allowed_states: res.allowed_states ?? [],
                transition_state: res.transition_state ?? "",
                requires_prior_output: res.requires_prior_output ?? false,
              },
            }));
          }
        })
        .catch(() => {});
    });
  }, [project.name, pinnedAgents]);

  function patchWorkflow(filename: string, key: keyof AgentWorkflowConfig, value: unknown) {
    setWorkflows((prev) => ({
      ...prev,
      [filename]: { ...(prev[filename] ?? { allowed_states: [], transition_state: "", requires_prior_output: false }), [key]: value },
    }));
  }

  async function saveWorkflow(filename: string) {
    const wf = workflows[filename];
    if (!wf) return;
    setSavingWorkflow(filename);
    try {
      await Projects.putAgentWorkflow(project.name, filename, wf);
    } catch { /* ignore */ }
    finally { setSavingWorkflow(null); }
  }

  async function loadMantisProjects() {
    const url      = (form.mantis_url || "").trim();
    const protocol = form.mantis_protocol || "rest";
    const token    = (form.mantis_token || "").trim();
    const username = (form.mantis_username || "").trim();
    const password = (form.mantis_password || "").trim();

    if (!url) {
      setMantisLoadError("Ingresá la URL de Mantis antes de cargar proyectos.");
      return;
    }
    if (protocol === "soap") {
      if (!username && !project.has_credentials) {
        setMantisLoadError("Ingresá el usuario de Mantis para SOAP.");
        return;
      }
    } else {
      if (!token && !project.has_credentials) {
        setMantisLoadError("Ingresá el token de Mantis antes de cargar proyectos.");
        return;
      }
    }

    setMantisLoading(true);
    setMantisLoadError(null);
    try {
      const params: MantisListParams = { url, protocol, verify_ssl: form.verify_ssl !== false };
      if (protocol === "soap") {
        params.username = username;
        params.password = password;
      } else {
        params.token = token;
      }
      const res = await Mantis.listProjects(params);
      if (res.ok) {
        setMantisProjects(res.projects);
        if (res.projects.length === 0) setMantisLoadError("No se encontraron proyectos accesibles.");
      } else {
        setMantisLoadError(res.error || "Error al conectar con Mantis");
      }
    } catch (e: any) {
      setMantisLoadError(e?.message || "Error de conexión");
    } finally {
      setMantisLoading(false);
    }
  }

  function patch(key: keyof InitProjectPayload, value: unknown) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  const isAdo    = form.tracker_type === "azure_devops";
  const isJira   = form.tracker_type === "jira";
  const isMantis = form.tracker_type === "mantis";

  async function handleSubmit() {
    setError(null);
    setSaving(true);
    try {
      const res = await Projects.update(project.name, form);
      if (res.ok) {
        onSaved();
      } else {
        setError((res as any).error || "Error desconocido");
      }
    } catch (e: any) {
      setError(e?.message || "Error de conexión");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.backdrop} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={styles.panel}>
        <h2 className={styles.title}>✎ Editar Proyecto: {project.display_name || project.name}</h2>

        <div className={styles.body}>
          <label className={styles.label}>Nombre para mostrar</label>
          <input
            className={styles.input}
            type="text"
            value={form.display_name ?? ""}
            onChange={(e) => patch("display_name", e.target.value)}
          />

          <label className={styles.label}>Workspace root</label>
          <input
            className={styles.input}
            type="text"
            placeholder="Ej: N:\GIT\RS\RSPacifico\trunk"
            value={form.workspace_root ?? ""}
            onChange={(e) => patch("workspace_root", e.target.value)}
          />

          <hr className={styles.divider} />

          <label className={styles.label}>Sistema de tickets</label>
          <div className={styles.trackerRow}>
            <button
              type="button"
              className={`${styles.trackerBtn} ${isAdo ? styles.trackerBtnActive : ""}`}
              onClick={() => patch("tracker_type", "azure_devops" as TrackerType)}
            >
              🔷 Azure DevOps
            </button>
            <button
              type="button"
              className={`${styles.trackerBtn} ${isJira ? styles.trackerBtnJira : ""}`}
              onClick={() => patch("tracker_type", "jira" as TrackerType)}
            >
              🔵 Jira
            </button>
            <button
              type="button"
              className={`${styles.trackerBtn} ${isMantis ? styles.trackerBtnMantis : ""}`}
              onClick={() => patch("tracker_type", "mantis" as TrackerType)}
            >
              🟢 Mantis BT
            </button>
          </div>

          {isAdo && (
            <div className={styles.trackerFields}>
              <span className={styles.trackerHeading}>🔷 Azure DevOps</span>
              <label className={styles.label}>Organización ADO</label>
              <input
                className={styles.input}
                type="text"
                value={form.organization ?? ""}
                onChange={(e) => patch("organization", e.target.value)}
              />
              <label className={styles.label}>Proyecto ADO</label>
              <input
                className={styles.input}
                type="text"
                value={form.ado_project ?? ""}
                onChange={(e) => patch("ado_project", e.target.value)}
              />
              <label className={styles.label}>Personal Access Token (PAT)</label>
              <input
                className={styles.input}
                type="password"
                placeholder={project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Pegá tu PAT de Azure DevOps"}
                value={form.pat ?? ""}
                onChange={(e) => patch("pat", e.target.value)}
              />
              <details className={styles.advanced}>
                <summary>🔍 Opciones avanzadas ADO</summary>
                <div className={styles.advancedBody}>
                  <label className={styles.labelSm}>Area Path (opcional)</label>
                  <input
                    className={styles.input}
                    type="text"
                    value={form.area_path ?? ""}
                    onChange={(e) => patch("area_path", e.target.value)}
                  />
                </div>
              </details>
            </div>
          )}

          {isJira && (
            <div className={styles.trackerFields}>
              <span className={`${styles.trackerHeading} ${styles.trackerHeadingJira}`}>🔵 Jira</span>
              <label className={styles.label}>URL de la instancia Jira</label>
              <input
                className={styles.input}
                type="text"
                value={form.jira_url ?? ""}
                onChange={(e) => patch("jira_url", e.target.value)}
              />
              <label className={styles.label}>Clave del proyecto</label>
              <input
                className={styles.input}
                type="text"
                value={form.jira_key ?? ""}
                onChange={(e) => patch("jira_key", e.target.value)}
              />
              <label className={styles.label}>Usuario / Email</label>
              <input
                className={styles.input}
                type="text"
                placeholder={loadedUser ? `${loadedUser} (usuario actual)` : "usuario@empresa.com"}
                value={form.jira_user ?? ""}
                onChange={(e) => patch("jira_user", e.target.value)}
              />
              <label className={styles.label}>API Token</label>
              <input
                className={styles.input}
                type="password"
                placeholder={project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Pegá tu API token de Jira"}
                value={form.jira_token ?? ""}
                onChange={(e) => patch("jira_token", e.target.value)}
              />
            </div>
          )}

          {isMantis && (
            <div className={styles.trackerFields}>
              <span className={`${styles.trackerHeading} ${styles.trackerHeadingMantis}`}>🟢 Mantis Bug Tracker</span>

              {/* Selector de protocolo */}
              <label className={styles.label}>Protocolo de conexión</label>
              <div className={styles.trackerRow}>
                <button
                  type="button"
                  className={`${styles.trackerBtn} ${form.mantis_protocol !== "soap" ? styles.trackerBtnActive : ""}`}
                  onClick={() => { patch("mantis_protocol", "rest"); setMantisProjects([]); setMantisLoadError(null); }}
                >
                  🔑 REST (Token API)
                </button>
                <button
                  type="button"
                  className={`${styles.trackerBtn} ${form.mantis_protocol === "soap" ? styles.trackerBtnActive : ""}`}
                  onClick={() => { patch("mantis_protocol", "soap"); setMantisProjects([]); setMantisLoadError(null); }}
                >
                  🔌 SOAP (Usuario/Contraseña)
                </button>
              </div>

              <label className={styles.label}>URL de la instancia Mantis</label>
              <input
                className={styles.input}
                type="text"
                placeholder="Ej: https://mantis.empresa.com"
                value={form.mantis_url ?? ""}
                onChange={(e) => patch("mantis_url", e.target.value)}
              />

              {/* Credenciales según protocolo */}
              {form.mantis_protocol === "soap" ? (
                <>
                  <label className={styles.label}>Usuario de Mantis</label>
                  <input
                    className={styles.input}
                    type="text"
                    placeholder={project.has_credentials ? "••••  (dejar vacío para no cambiar)" : "Usuario de Mantis"}
                    value={form.mantis_username ?? ""}
                    onChange={(e) => patch("mantis_username", e.target.value)}
                  />
                  <label className={styles.label}>Contraseña</label>
                  <input
                    className={styles.input}
                    type="password"
                    placeholder={project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Contraseña de Mantis"}
                    value={form.mantis_password ?? ""}
                    onChange={(e) => patch("mantis_password", e.target.value)}
                  />
                </>
              ) : (
                <>
                  <label className={styles.label}>API Token</label>
                  <input
                    className={styles.input}
                    type="password"
                    placeholder={project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Token de API de Mantis"}
                    value={form.mantis_token ?? ""}
                    onChange={(e) => patch("mantis_token", e.target.value)}
                  />
                </>
              )}

              <button
                type="button"
                className={styles.btnLoadProjects}
                onClick={loadMantisProjects}
                disabled={mantisLoading}
              >
                {mantisLoading ? "Cargando proyectos…" : "🔄 Cargar proyectos de Mantis"}
              </button>

              {mantisLoadError && (
                <div className={styles.errorSmall}>{mantisLoadError}</div>
              )}

              {mantisProjects.length > 0 && (
                <>
                  <label className={styles.label}>Proyecto Mantis</label>
                  <select
                    className={styles.select}
                    value={form.mantis_project_id ?? ""}
                    onChange={(e) => {
                      const selected = mantisProjects.find((p) => p.id === e.target.value);
                      patch("mantis_project_id", e.target.value);
                      patch("mantis_project_name", selected?.name ?? "");
                    }}
                  >
                    <option value="">— Seleccioná un proyecto —</option>
                    {mantisProjects.map((p) => (
                      <option key={p.id} value={p.id}>
                        #{p.id} — {p.name}
                        {p.description ? ` (${p.description.slice(0, 40)})` : ""}
                      </option>
                    ))}
                  </select>
                </>
              )}

              {/* Muestra el proyecto actual si no se cargó la lista */}
              {!mantisProjects.length && (form.mantis_project_id || form.mantis_project_name) && (
                <p className={styles.note}>
                  Proyecto actual: <strong>{form.mantis_project_name || `#${form.mantis_project_id}`}</strong>
                  {" — "}Cargá proyectos para cambiar la selección.
                </p>
              )}
            </div>
          )}

          {error && <div className={styles.error}>{error}</div>}

          {/* ── Workflow por agente ─────────────────────────────── */}
          {pinnedAgents.length > 0 && (
            <>
              <hr className={styles.divider} />
              <span className={styles.trackerHeading}>⚙️ Workflow por agente</span>
              <p style={{ fontSize: 12, color: "var(--text-muted, #999)", marginTop: 4, marginBottom: 12 }}>
                Configurá qué estados puede ver cada agente, a qué estado debe mover el ticket al terminar, y si requiere output anterior.
              </p>
              {pinnedAgents.map((filename) => {
                const wf = workflows[filename] ?? { allowed_states: [], transition_state: "", requires_prior_output: false };
                const label = filename.replace(/\.agent\.md$/i, "").replace(/_/g, " ");
                return (
                  <details key={filename} className={styles.advanced} style={{ marginBottom: 8 }}>
                    <summary style={{ fontWeight: 600, cursor: "pointer" }}>🤖 {label}</summary>
                    <div className={styles.advancedBody}>
                      <label className={styles.labelSm}>Estados visibles (allowed_states)</label>
                      <p style={{ fontSize: 11, color: "var(--text-muted, #999)", margin: "2px 0 6px" }}>
                        Estados del tracker que este agente puede procesar. Uno por línea.
                        {trackerStates.length > 0 && (
                          <> Disponibles: <strong>{trackerStates.join(", ")}</strong></>
                        )}
                      </p>
                      <textarea
                        className={styles.input}
                        rows={3}
                        style={{ resize: "vertical", fontFamily: "monospace", fontSize: 12 }}
                        value={wf.allowed_states.join("\n")}
                        onChange={(e) =>
                          patchWorkflow(filename, "allowed_states",
                            e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))
                        }
                      />

                      <label className={styles.labelSm} style={{ marginTop: 8 }}>Estado de transición (transition_state)</label>
                      <p style={{ fontSize: 11, color: "var(--text-muted, #999)", margin: "2px 0 6px" }}>
                        Estado al que se moverá el ticket cuando el agente termine.
                      </p>
                      {trackerStates.length > 0 ? (
                        <select
                          className={styles.input}
                          value={wf.transition_state}
                          onChange={(e) => patchWorkflow(filename, "transition_state", e.target.value)}
                        >
                          <option value="">— Sin transición automática —</option>
                          {trackerStates.map((s) => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          className={styles.input}
                          type="text"
                          placeholder="Ej: In Progress"
                          value={wf.transition_state}
                          onChange={(e) => patchWorkflow(filename, "transition_state", e.target.value)}
                        />
                      )}

                      <label className={styles.labelSm} style={{ marginTop: 8 }}>
                        <input
                          type="checkbox"
                          style={{ marginRight: 6 }}
                          checked={wf.requires_prior_output}
                          onChange={(e) => patchWorkflow(filename, "requires_prior_output", e.target.checked)}
                        />
                        Requiere output del agente anterior (requires_prior_output)
                      </label>

                      <button
                        type="button"
                        className={styles.btnAccent}
                        style={{ marginTop: 10, fontSize: 12, padding: "4px 14px" }}
                        disabled={savingWorkflow === filename}
                        onClick={() => saveWorkflow(filename)}
                      >
                        {savingWorkflow === filename ? "Guardando…" : "💾 Guardar workflow"}
                      </button>
                    </div>
                  </details>
                );
              })}
            </>
          )}
        </div>

        <div className={styles.footer}>
          <button
            className={styles.btnDanger}
            onClick={onDelete}
            disabled={saving}
            style={{ marginRight: "auto" }}
          >
            🗑 Eliminar
          </button>
          <button className={styles.btnGhost} onClick={onClose} disabled={saving}>
            Cancelar
          </button>
          <button className={styles.btnAccent} onClick={handleSubmit} disabled={saving}>
            {saving ? "Guardando…" : "Guardar cambios"}
          </button>
        </div>
      </div>
    </div>
  );
}
