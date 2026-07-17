import React, { useState, useEffect } from "react";
import { Projects, Mantis, type MantisProject, type MantisListParams } from "../api/endpoints";
import type { AgentWorkflowConfig, InitProjectPayload, Project, TrackerType } from "../types";
import { formatLoadErrorMessage } from "../utils/loadError";
import { shouldCloseOnBackdrop } from "../services/uiGuards";
import { Field, Input, Select, Textarea, Checkbox, firstErrorFieldId } from "./ui";
import useOptimisticPending from "../hooks/useOptimisticPending";
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
    agents_dir:           project.agents_dir ?? "",
    docs_paths:           project.docs_paths ?? { technical: "", functional: "" },
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
    gitlab_url:           project.gitlab_url ?? "",
    gitlab_project:       project.gitlab_project ?? "",
    gitlab_group:         project.gitlab_group ?? "",
    gitlab_auth_file:     project.gitlab_auth_file ?? "",
  });
  const { pending: saving, run, pendingClass } = useOptimisticPending();
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  // Plan 136 F2 — hay cambios tipeados sin guardar (protege el backdrop).
  const [dirty, setDirty] = useState(false);
  const [loadedUser, setLoadedUser] = useState<string | null>(null);
  const [docsChecking, setDocsChecking] = useState(false);
  const [docsCheckMessage, setDocsCheckMessage] = useState<string | null>(null);

  // Mantis: listar proyectos disponibles
  const [mantisProjects, setMantisProjects] = useState<MantisProject[]>([]);
  const [mantisLoading, setMantisLoading] = useState(false);
  const [mantisLoadError, setMantisLoadError] = useState<string | null>(null);

  // Workflow por agente
  const [pinnedAgents, setPinnedAgents] = useState<string[]>([]);
  const [trackerStates, setTrackerStates] = useState<string[]>([]);
  const [workflows, setWorkflows] = useState<Record<string, AgentWorkflowConfig>>({});
  const [savingWorkflow, setSavingWorkflow] = useState<string | null>(null);
  const [workflowSaveError, setWorkflowSaveError] =
    useState<{ filename: string; message: string } | null>(null);

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
    setWorkflowSaveError(null);
    try {
      await Projects.putAgentWorkflow(project.name, filename, wf);
    } catch (e) {
      // Plan 135 F7: antes el catch tragaba el error silenciosamente — el
      // operador creía que guardó. El estado local `workflows` se conserva
      // => reintento 1-click.
      setWorkflowSaveError({ filename, message: formatLoadErrorMessage(e) });
    } finally {
      setSavingWorkflow(null);
    }
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
    setDirty(true);
    setFieldErrors((fe) => {
      if (!(key in fe)) return fe;
      const next = { ...fe };
      delete next[key as string];
      return next;
    });
  }

  function docsPath(kind: "technical" | "functional"): string {
    return form.docs_paths?.[kind] ?? "";
  }

  function patchDocsPath(kind: "technical" | "functional", value: string) {
    setForm((f) => ({
      ...f,
      docs_paths: {
        technical: f.docs_paths?.technical ?? "",
        functional: f.docs_paths?.functional ?? "",
        [kind]: value,
      },
    }));
    setDocsCheckMessage(null);
    setDirty(true);
  }

  function buildPayload(): Partial<InitProjectPayload> {
    const docs_paths = {
      technical: docsPath("technical").trim(),
      functional: docsPath("functional").trim(),
    };
    return { ...form, docs_paths };
  }

  async function browseAgentsDir() {
    setError(null);
    try {
      const res = await Projects.browseFolder({
        title: "Seleccionar carpeta de agentes",
        initial_dir: String(form.agents_dir || form.workspace_root || ""),
      });
      if (res.ok && res.path) {
        patch("agents_dir", res.path);
      } else if (!res.ok) {
        setError(res.error || "No se pudo abrir el selector de carpeta");
      }
    } catch (e: any) {
      setError(e?.message || "No se pudo abrir el selector de carpeta");
    }
  }

  async function browseDocsPath(kind: "technical" | "functional") {
    setError(null);
    const currentPath = docsPath(kind);
    try {
      const res = await Projects.browseFolder({
        title: kind === "technical" ? "Seleccionar documentación técnica" : "Seleccionar documentación funcional / manual",
        initial_dir: String(currentPath || form.workspace_root || ""),
      });
      if (res.ok && res.path) {
        patchDocsPath(kind, res.path);
      } else if (!res.ok) {
        setError(res.error || "No se pudo abrir el selector de carpeta");
      }
    } catch (e: any) {
      setError(e?.message || "No se pudo abrir el selector de carpeta");
    }
  }

  async function testDocsPaths() {
    setError(null);
    setDocsCheckMessage(null);
    const payload = buildPayload();
    if (!payload.docs_paths?.technical && !payload.docs_paths?.functional) {
      setDocsCheckMessage("Sin rutas configuradas: Stacky usará autodiscovery en workspace_root/docs.");
      return;
    }
    setDocsChecking(true);
    try {
      const res = await Projects.testDocsPaths(project.name, payload);
      const tech = res.counts.technical;
      const functional = res.counts.functional;
      setDocsCheckMessage(
        `Técnica: ${tech.total} archivos (${tech.md} .md, ${tech.pdf} .pdf). ` +
        `Funcional: ${functional.total} archivos (${functional.md} .md, ${functional.pdf} .pdf).`
      );
    } catch (e: any) {
      setError(e?.message || "No se pudieron validar las rutas de documentación");
    } finally {
      setDocsChecking(false);
    }
  }

  const isAdo    = form.tracker_type === "azure_devops";
  const isJira   = form.tracker_type === "jira";
  const isMantis = form.tracker_type === "mantis";
  const isGitlab = form.tracker_type === "gitlab";

  function validate(f: typeof form): Record<string, string> {
    const errs: Record<string, string> = {};
    if (!String(f.workspace_root ?? "").trim()) errs.workspace_root = "Ingresá el workspace root";
    return errs;
  }

  // [ADICIÓN ARQUITECTO] Orden VISUAL del form (para foco-al-primer-error).
  const EP_FIELD_DOM_ORDER = ["workspace_root"] as const;

  async function handleSubmit() {
    setError(null);
    const errs = validate(form);
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) {
      // [ADICIÓN ARQUITECTO] foco al primer campo con error.
      const fid = firstErrorFieldId("ep", EP_FIELD_DOM_ORDER, errs);
      if (fid) document.getElementById(fid)?.focus();
      return;
    }
    try {
      const res = await run(() => Projects.update(project.name, buildPayload()));
      if (res.ok) {
        onSaved();
      } else {
        setError((res as any).error || "Error desconocido");
      }
    } catch (e: any) {
      setError(e?.message || "Error de conexión");
    }
  }

  return (
    <div className={styles.backdrop} onClick={(e) => { if (e.target === e.currentTarget && shouldCloseOnBackdrop({ dirty, busy: saving })) onClose(); }}>
      <div className={styles.panel}>
        <h2 className={styles.title}>✎ Editar Proyecto: {project.display_name || project.name}</h2>

        <div className={styles.body}>
          <Field label="Nombre para mostrar" labelClassName={styles.label}>
            {(ctl) => (
              <Input
                {...ctl}
                className={styles.input}
                type="text"
                value={form.display_name ?? ""}
                onChange={(e) => patch("display_name", e.target.value)}
              />
            )}
          </Field>

          <Field label="Workspace root" labelClassName={styles.label} error={fieldErrors.workspace_root} id="ep-workspace_root">
            {(ctl) => (
              <Input
                {...ctl}
                invalid={Boolean(fieldErrors.workspace_root)}
                className={styles.input}
                type="text"
                placeholder="Ej: C:\Repos\MiProyecto\trunk"
                value={form.workspace_root ?? ""}
                onChange={(e) => patch("workspace_root", e.target.value)}
              />
            )}
          </Field>

          <Field label="Carpeta de agentes" labelClassName={styles.label}>
            {(ctl) => (
              <div className={styles.pathRow}>
                <Input
                  {...ctl}
                  className={styles.input}
                  type="text"
                  placeholder="Vacío = Stacky/agents"
                  value={form.agents_dir ?? ""}
                  onChange={(e) => patch("agents_dir", e.target.value)}
                />
                <button type="button" className={styles.btnPath} onClick={browseAgentsDir}>
                  Examinar...
                </button>
              </div>
            )}
          </Field>

          <div className={styles.docsPathSection}>
            <span className={styles.trackerHeading}>Documentación del proyecto (opcional)</span>
            <p className={styles.note}>
              Estas rutas reemplazan el autodiscovery de <code>docs/</code> para el panel Docs.
            </p>

            <Field label="Documentación técnica" labelClassName={styles.label}>
              {(ctl) => (
                <div className={styles.pathRow}>
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: C:\Docs\MiProyecto\tecnica"
                    value={docsPath("technical")}
                    onChange={(e) => patchDocsPath("technical", e.target.value)}
                  />
                  <button type="button" className={styles.btnPath} onClick={() => browseDocsPath("technical")}>
                    Examinar...
                  </button>
                </div>
              )}
            </Field>

            <Field label="Documentación funcional / manual" labelClassName={styles.label}>
              {(ctl) => (
                <div className={styles.pathRow}>
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: C:\Docs\MiProyecto\funcional"
                    value={docsPath("functional")}
                    onChange={(e) => patchDocsPath("functional", e.target.value)}
                  />
                  <button type="button" className={styles.btnPath} onClick={() => browseDocsPath("functional")}>
                    Examinar...
                  </button>
                </div>
              )}
            </Field>

            <div className={styles.docsActions}>
              <button type="button" className={styles.btnLoadProjects} onClick={testDocsPaths} disabled={docsChecking}>
                {docsChecking ? "Validando..." : "Probar rutas docs"}
              </button>
              {docsCheckMessage && <span className={styles.docsCheckOk}>{docsCheckMessage}</span>}
            </div>
          </div>

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
            <button
              type="button"
              className={`${styles.trackerBtn} ${isGitlab ? styles.trackerBtnActive : ""}`}
              onClick={() => patch("tracker_type", "gitlab" as TrackerType)}
            >
              🦊 GitLab
            </button>
          </div>

          {isAdo && (
            <div className={styles.trackerFields}>
              <span className={styles.trackerHeading}>🔷 Azure DevOps</span>
              <Field label="Organización ADO" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    value={form.organization ?? ""}
                    onChange={(e) => patch("organization", e.target.value)}
                  />
                )}
              </Field>
              <Field label="Proyecto ADO" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    value={form.ado_project ?? ""}
                    onChange={(e) => patch("ado_project", e.target.value)}
                  />
                )}
              </Field>
              <Field label="Personal Access Token (PAT)" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="password"
                    placeholder={project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Pegá tu PAT de Azure DevOps"}
                    value={form.pat ?? ""}
                    onChange={(e) => patch("pat", e.target.value)}
                  />
                )}
              </Field>
              <details className={styles.advanced}>
                <summary>🔍 Opciones avanzadas ADO</summary>
                <div className={styles.advancedBody}>
                  <Field label="Area Path (opcional)" labelClassName={styles.labelSm}>
                    {(ctl) => (
                      <Input
                        {...ctl}
                        className={styles.input}
                        type="text"
                        value={form.area_path ?? ""}
                        onChange={(e) => patch("area_path", e.target.value)}
                      />
                    )}
                  </Field>
                </div>
              </details>
            </div>
          )}

          {isJira && (
            <div className={styles.trackerFields}>
              <span className={`${styles.trackerHeading} ${styles.trackerHeadingJira}`}>🔵 Jira</span>
              <Field label="URL de la instancia Jira" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    value={form.jira_url ?? ""}
                    onChange={(e) => patch("jira_url", e.target.value)}
                  />
                )}
              </Field>
              <Field label="Clave del proyecto" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    value={form.jira_key ?? ""}
                    onChange={(e) => patch("jira_key", e.target.value)}
                  />
                )}
              </Field>
              <Field label="Usuario / Email" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    placeholder={loadedUser ? `${loadedUser} (usuario actual)` : "usuario@empresa.com"}
                    value={form.jira_user ?? ""}
                    onChange={(e) => patch("jira_user", e.target.value)}
                  />
                )}
              </Field>
              <Field label="API Token" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="password"
                    placeholder={project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Pegá tu API token de Jira"}
                    value={form.jira_token ?? ""}
                    onChange={(e) => patch("jira_token", e.target.value)}
                  />
                )}
              </Field>
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

              <Field label="URL de la instancia Mantis" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: https://mantis.empresa.com"
                    value={form.mantis_url ?? ""}
                    onChange={(e) => patch("mantis_url", e.target.value)}
                  />
                )}
              </Field>

              {/* Credenciales según protocolo */}
              {form.mantis_protocol === "soap" ? (
                <>
                  <Field label="Usuario de Mantis" labelClassName={styles.label}>
                    {(ctl) => (
                      <Input
                        {...ctl}
                        className={styles.input}
                        type="text"
                        placeholder={project.has_credentials ? "••••  (dejar vacío para no cambiar)" : "Usuario de Mantis"}
                        value={form.mantis_username ?? ""}
                        onChange={(e) => patch("mantis_username", e.target.value)}
                      />
                    )}
                  </Field>
                  <Field label="Contraseña" labelClassName={styles.label}>
                    {(ctl) => (
                      <Input
                        {...ctl}
                        className={styles.input}
                        type="password"
                        placeholder={project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Contraseña de Mantis"}
                        value={form.mantis_password ?? ""}
                        onChange={(e) => patch("mantis_password", e.target.value)}
                      />
                    )}
                  </Field>
                </>
              ) : (
                <>
                  <Field label="API Token" labelClassName={styles.label}>
                    {(ctl) => (
                      <Input
                        {...ctl}
                        className={styles.input}
                        type="password"
                        placeholder={project.has_credentials ? "••••••••  (dejar vacío para no cambiar)" : "Token de API de Mantis"}
                        value={form.mantis_token ?? ""}
                        onChange={(e) => patch("mantis_token", e.target.value)}
                      />
                    )}
                  </Field>
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
                  <Field label="Proyecto Mantis" labelClassName={styles.label}>
                    {(ctl) => (
                      <Select
                        {...ctl}
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
                      </Select>
                    )}
                  </Field>
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

          {isGitlab && (
            <div className={styles.trackerFields}>
              <span className={styles.trackerHeading}>🦊 GitLab</span>
              <p className={styles.note}>
                El token de acceso se lee del archivo de autenticación. Nunca se guarda en el perfil.
              </p>
              <Field label="URL base del GitLab" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: https://gitlab.com"
                    value={form.gitlab_url ?? ""}
                    onChange={(e) => patch("gitlab_url", e.target.value)}
                  />
                )}
              </Field>
              <Field label="Proyecto (namespace/repo)" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: mi-org/mi-repo"
                    value={form.gitlab_project ?? ""}
                    onChange={(e) => patch("gitlab_project", e.target.value)}
                  />
                )}
              </Field>
              <Field label="Grupo (opcional, para Epics nativos)" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: mi-org"
                    value={form.gitlab_group ?? ""}
                    onChange={(e) => patch("gitlab_group", e.target.value)}
                  />
                )}
              </Field>
              <Field label="Ruta al archivo de token" labelClassName={styles.label}>
                {(ctl) => (
                  <Input
                    {...ctl}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: C:\secrets\gitlab_token.txt"
                    value={form.gitlab_auth_file ?? ""}
                    onChange={(e) => patch("gitlab_auth_file", e.target.value)}
                  />
                )}
              </Field>
              <p className={styles.note}>
                El archivo debe contener solo el token en texto plano (sin comillas ni saltos de línea extra).
              </p>
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
                      <Field label="Estados visibles (allowed_states)" labelClassName={styles.labelSm}>
                        {(ctl) => (
                          <>
                            <p style={{ fontSize: 11, color: "var(--text-muted, #999)", margin: "2px 0 6px" }}>
                              Estados del tracker que este agente puede procesar. Uno por línea.
                              {trackerStates.length > 0 && (
                                <> Disponibles: <strong>{trackerStates.join(", ")}</strong></>
                              )}
                            </p>
                            <Textarea
                              {...ctl}
                              className={styles.input}
                              rows={3}
                              style={{ resize: "vertical", fontFamily: "monospace", fontSize: 12 }}
                              value={wf.allowed_states.join("\n")}
                              onChange={(e) =>
                                patchWorkflow(filename, "allowed_states",
                                  e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))
                              }
                            />
                          </>
                        )}
                      </Field>

                      <Field label="Estado de transición (transition_state)" labelClassName={styles.labelSm} labelStyle={{ marginTop: 8 }}>
                        {(ctl) => (
                          <>
                            <p style={{ fontSize: 11, color: "var(--text-muted, #999)", margin: "2px 0 6px" }}>
                              Estado al que se moverá el ticket cuando el agente termine.
                            </p>
                            {trackerStates.length > 0 ? (
                              <Select
                                {...ctl}
                                className={styles.input}
                                value={wf.transition_state}
                                onChange={(e) => patchWorkflow(filename, "transition_state", e.target.value)}
                              >
                                <option value="">— Sin transición automática —</option>
                                {trackerStates.map((s) => (
                                  <option key={s} value={s}>{s}</option>
                                ))}
                              </Select>
                            ) : (
                              <Input
                                {...ctl}
                                className={styles.input}
                                type="text"
                                placeholder="Ej: In Progress"
                                value={wf.transition_state}
                                onChange={(e) => patchWorkflow(filename, "transition_state", e.target.value)}
                              />
                            )}
                          </>
                        )}
                      </Field>

                      <Checkbox
                        labelClassName={styles.labelSm}
                        labelStyle={{ marginTop: 8 }}
                        style={{ marginRight: 6 }}
                        checked={wf.requires_prior_output}
                        onChange={(e) => patchWorkflow(filename, "requires_prior_output", e.target.checked)}
                        label="Requiere output del agente anterior (requires_prior_output)"
                      />

                      <button
                        type="button"
                        className={styles.btnAccent}
                        style={{ marginTop: 10, fontSize: 12, padding: "4px 14px" }}
                        disabled={savingWorkflow === filename}
                        onClick={() => saveWorkflow(filename)}
                      >
                        {savingWorkflow === filename ? "Guardando…" : "💾 Guardar workflow"}
                      </button>
                      {workflowSaveError?.filename === filename && (
                        <div role="alert" className={styles.saveError}>
                          No se pudo guardar el workflow: {workflowSaveError.message}. Tus cambios siguen en el formulario — reintentá.
                        </div>
                      )}
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
          <button
            className={`${styles.btnAccent} ${pendingClass}`.trim()}
            onClick={handleSubmit}
            disabled={saving}
            aria-busy={saving || undefined}
          >
            {saving ? "Guardando…" : "Guardar cambios"}
          </button>
        </div>
      </div>
    </div>
  );
}
