import React, { useState } from "react";
import { Projects, Mantis, type MantisProject, type MantisListParams } from "../api/endpoints";
import type { InitProjectPayload, TrackerType } from "../types";
import { Field, Input, Select, Textarea, Checkbox, firstErrorFieldId } from "./ui";
import useOptimisticPending from "../hooks/useOptimisticPending";
import styles from "./NewProjectModal.module.css";

interface Props {
  onClose: () => void;
  onCreated: (projectName: string, displayName: string) => void;
}

const EMPTY: InitProjectPayload = {
  name: "",
  display_name: "",
  workspace_root: "",
  agents_dir: "",
  docs_paths: { technical: "", functional: "" },
  tracker_type: "azure_devops",
  organization: "",
  ado_project: "",
  area_path: "",
  pat: "",
  jira_url: "",
  jira_key: "",
  api_version: "3",
  jql: "",
  verify_ssl: true,
  jira_user: "",
  jira_token: "",
  mantis_url: "",
  mantis_project_id: "",
  mantis_project_name: "",
  mantis_protocol: "rest",
  mantis_token: "",
  mantis_username: "",
  mantis_password: "",
};

export default function NewProjectModal({ onClose, onCreated }: Props) {
  const [form, setForm] = useState<InitProjectPayload>({ ...EMPTY });
  const { pending: saving, run, pendingClass } = useOptimisticPending();
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [docsChecking, setDocsChecking] = useState(false);
  const [docsCheckMessage, setDocsCheckMessage] = useState<string | null>(null);

  // Mantis: listar proyectos disponibles
  const [mantisProjects, setMantisProjects] = useState<MantisProject[]>([]);
  const [mantisLoading, setMantisLoading] = useState(false);
  const [mantisLoadError, setMantisLoadError] = useState<string | null>(null);

  function patch(key: keyof InitProjectPayload, value: unknown) {
    setForm((f) => ({ ...f, [key]: value }));
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
  }

  function buildPayload(): InitProjectPayload {
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
        initial_dir: form.agents_dir || form.workspace_root || "",
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
        initial_dir: currentPath || form.workspace_root || "",
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
      setDocsCheckMessage("No configuraste rutas de documentación. Stacky usará autodiscovery en workspace_root/docs.");
      return;
    }
    setDocsChecking(true);
    try {
      const res = await Projects.testDocsPaths(form.name.trim() || "_new", payload);
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

  function setTrackerType(type: TrackerType) {
    setForm((f) => ({ ...f, tracker_type: type }));
    // Reset mantis project list when switching away
    if (type !== "mantis") {
      setMantisProjects([]);
      setMantisLoadError(null);
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
    if (protocol === "soap" && !username) {
      setMantisLoadError("Ingresá el usuario de Mantis para SOAP.");
      return;
    }
    if (protocol !== "soap" && !token) {
      setMantisLoadError("Ingresá el token de API de Mantis.");
      return;
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

  function validate(f: InitProjectPayload): Record<string, string> {
    const errs: Record<string, string> = {};
    if (!f.name.trim()) errs.name = "Ingresá un nombre de proyecto";
    if (!f.workspace_root.trim()) errs.workspace_root = "Ingresá el workspace root";
    if (f.tracker_type === "azure_devops") {
      if (!f.organization?.trim()) errs.organization = "Ingresá la organización de Azure DevOps";
      if (!f.ado_project?.trim()) errs.ado_project = "Ingresá el proyecto de Azure DevOps";
    } else if (f.tracker_type === "jira") {
      if (!f.jira_url?.trim()) errs.jira_url = "Ingresá la URL de Jira";
      if (!f.jira_key?.trim()) errs.jira_key = "Ingresá la clave del proyecto Jira";
    } else {
      if (!f.mantis_url?.trim()) errs.mantis_url = "Ingresá la URL de Mantis";
      if (!f.mantis_project_id?.trim()) errs.mantis_project_id = "Seleccioná un proyecto de Mantis";
      const protocol = f.mantis_protocol || "rest";
      if (protocol === "soap") {
        if (!f.mantis_username?.trim()) errs.mantis_username = "Ingresá el usuario de Mantis (SOAP)";
      } else {
        if (!f.mantis_token?.trim()) errs.mantis_token = "Ingresá el token de API de Mantis";
      }
    }
    return errs;
  }

  // [ADICIÓN ARQUITECTO] Orden VISUAL del form (para foco-al-primer-error).
  const NP_FIELD_DOM_ORDER = ["name", "workspace_root", "organization", "ado_project", "jira_url", "jira_key", "mantis_url", "mantis_project_id", "mantis_username", "mantis_token"] as const;

  async function handleSubmit() {
    setError(null);
    const errs = validate(form);
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) {
      // [ADICIÓN ARQUITECTO] foco al primer campo con error.
      const fid = firstErrorFieldId("np", NP_FIELD_DOM_ORDER, errs);
      if (fid) document.getElementById(fid)?.focus();
      return;
    }
    try {
      const result = await run(() => Projects.init(buildPayload()));
      if (result.ok) {
        onCreated(result.project.name, result.project.display_name);
        onClose();
      } else {
        setError((result as any).error || "Error desconocido");
      }
    } catch (e: any) {
      setError(e?.message || "Error de conexión");
    }
  }

    const isAdo    = form.tracker_type === "azure_devops";
  const isJira   = form.tracker_type === "jira";
  const isMantis = form.tracker_type === "mantis";

  return (
    <div className={styles.backdrop} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={styles.panel}>
        <h2 className={styles.title}>📁 Inicializar Nuevo Proyecto</h2>

        <div className={styles.body}>
          {/* Nombre / display */}
          <Field label="Nombre interno del proyecto (ID, en mayúsculas)" labelClassName={styles.label} error={fieldErrors.name} id="np-name">
            {(ctl) => (
              <Input
                {...ctl}
                invalid={Boolean(fieldErrors.name)}
                className={styles.input}
                type="text"
                placeholder="Ej: RSPACIFICO, B2IMPACT"
                value={form.name}
                onChange={(e) => patch("name", e.target.value.toUpperCase())}
              />
            )}
          </Field>

          <Field label="Nombre para mostrar" labelClassName={styles.label}>
            {(ctl) => (
              <Input
                {...ctl}
                className={styles.input}
                type="text"
                placeholder="Ej: RS Pacífico"
                value={form.display_name ?? ""}
                onChange={(e) => patch("display_name", e.target.value)}
              />
            )}
          </Field>

          <Field label="Workspace root (ruta al código fuente)" labelClassName={styles.label} error={fieldErrors.workspace_root} id="np-workspace_root">
            {(ctl) => (
              <Input
                {...ctl}
                invalid={Boolean(fieldErrors.workspace_root)}
                className={styles.input}
                type="text"
                placeholder="Ej: C:\Repos\MiProyecto\trunk"
                value={form.workspace_root}
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
              Si dejás ambas vacías, Stacky mantiene el autodiscovery actual de carpetas <code>docs/</code>.
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

          {/* Selector de tracker */}
          <label className={styles.label}>Sistema de tickets</label>
          <div className={styles.trackerRow}>
            <button
              type="button"
              className={`${styles.trackerBtn} ${isAdo ? styles.trackerBtnActive : ""}`}
              onClick={() => setTrackerType("azure_devops")}
            >
              🔷 Azure DevOps
            </button>
            <button
              type="button"
              className={`${styles.trackerBtn} ${isJira ? styles.trackerBtnJira : ""}`}
              onClick={() => setTrackerType("jira")}
            >
              🔵 Jira
            </button>
            <button
              type="button"
              className={`${styles.trackerBtn} ${isMantis ? styles.trackerBtnMantis : ""}`}
              onClick={() => setTrackerType("mantis")}
            >
              🟢 Mantis BT
            </button>
          </div>

          {/* Campos ADO */}
          {isAdo && (
            <div className={styles.trackerFields}>
              <span className={styles.trackerHeading}>🔷 Azure DevOps</span>
              <Field label="Organización ADO" labelClassName={styles.label} error={fieldErrors.organization} id="np-organization">
                {(ctl) => (
                  <Input
                    {...ctl}
                    invalid={Boolean(fieldErrors.organization)}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: UbimiaPacifico"
                    value={form.organization ?? ""}
                    onChange={(e) => patch("organization", e.target.value)}
                  />
                )}
              </Field>
              <Field label="Proyecto ADO" labelClassName={styles.label} error={fieldErrors.ado_project} id="np-ado_project">
                {(ctl) => (
                  <Input
                    {...ctl}
                    invalid={Boolean(fieldErrors.ado_project)}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: Strategist_Pacifico"
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
                    placeholder="Pegá tu PAT de Azure DevOps"
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
                        placeholder="Ej: Strategist_Pacifico\AgendaWeb"
                        value={form.area_path ?? ""}
                        onChange={(e) => patch("area_path", e.target.value)}
                      />
                    )}
                  </Field>
                </div>
              </details>
            </div>
          )}

          {/* Campos Jira */}
          {isJira && (
            <div className={styles.trackerFields}>
              <span className={`${styles.trackerHeading} ${styles.trackerHeadingJira}`}>🔵 Jira</span>
              <Field label="URL de la instancia Jira" labelClassName={styles.label} error={fieldErrors.jira_url} id="np-jira_url">
                {(ctl) => (
                  <Input
                    {...ctl}
                    invalid={Boolean(fieldErrors.jira_url)}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: https://empresa.atlassian.net  o  https://jira.intranet.com"
                    value={form.jira_url ?? ""}
                    onChange={(e) => patch("jira_url", e.target.value)}
                  />
                )}
              </Field>
              <Field label="Clave del proyecto (project key)" labelClassName={styles.label} error={fieldErrors.jira_key} id="np-jira_key">
                {(ctl) => (
                  <Input
                    {...ctl}
                    invalid={Boolean(fieldErrors.jira_key)}
                    className={styles.input}
                    type="text"
                    placeholder="Ej: B2IM, PROJ, DEV"
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
                    placeholder="Ej: me@empresa.com"
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
                    placeholder="Pegá tu API token de Jira"
                    value={form.jira_token ?? ""}
                    onChange={(e) => patch("jira_token", e.target.value)}
                  />
                )}
              </Field>
              <details className={styles.advanced}>
                <summary className={styles.advancedJira}>🔍 Opciones avanzadas Jira</summary>
                <div className={styles.advancedBody}>
                  <Field label="Versión API" labelClassName={styles.labelSm}>
                    {(ctl) => (
                      <Select
                        {...ctl}
                        className={styles.select}
                        value={form.api_version ?? "3"}
                        onChange={(e) => patch("api_version", e.target.value)}
                      >
                        <option value="3">v3 — Jira Cloud (*.atlassian.net)</option>
                        <option value="2">v2 — Jira Server / Data Center</option>
                      </Select>
                    )}
                  </Field>
                  <Field label="JQL personalizado (opcional)" labelClassName={styles.labelSm}>
                    {(ctl) => (
                      <Textarea
                        {...ctl}
                        className={styles.textarea}
                        placeholder="Ej: assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
                        value={form.jql ?? ""}
                        onChange={(e) => patch("jql", e.target.value)}
                      />
                    )}
                  </Field>
                  <Checkbox
                    labelClassName={styles.checkboxRow}
                    checked={form.verify_ssl === false}
                    onChange={(e) => patch("verify_ssl", !e.target.checked)}
                    label="Desactivar verificación SSL (redes corporativas con CA custom)"
                  />
                </div>
              </details>
              <p className={styles.note}>
                Las credenciales se guardan cifradas en <code>backend/projects/{"{nombre}"}/auth/jira_auth.json</code>.
              </p>
            </div>
          )}

          {/* Campos Mantis */}
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

              <Field label="URL de la instancia Mantis" labelClassName={styles.label} error={fieldErrors.mantis_url} id="np-mantis_url">
                {(ctl) => (
                  <Input
                    {...ctl}
                    invalid={Boolean(fieldErrors.mantis_url)}
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
                  <Field label="Usuario de Mantis" labelClassName={styles.label} error={fieldErrors.mantis_username} id="np-mantis_username">
                    {(ctl) => (
                      <Input
                        {...ctl}
                        invalid={Boolean(fieldErrors.mantis_username)}
                        className={styles.input}
                        type="text"
                        placeholder="Usuario de Mantis (ej: admin)"
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
                        placeholder="Contraseña de Mantis"
                        value={form.mantis_password ?? ""}
                        onChange={(e) => patch("mantis_password", e.target.value)}
                      />
                    )}
                  </Field>
                </>
              ) : (
                <>
                  <Field label="API Token" labelClassName={styles.label} error={fieldErrors.mantis_token} id="np-mantis_token">
                    {(ctl) => (
                      <Input
                        {...ctl}
                        invalid={Boolean(fieldErrors.mantis_token)}
                        className={styles.input}
                        type="password"
                        placeholder="Token de API de Mantis (Mi Cuenta → Tokens API)"
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
                  <Field label="Proyecto Mantis" labelClassName={styles.label} error={fieldErrors.mantis_project_id} id="np-mantis_project_id">
                    {(ctl) => (
                      <Select
                        {...ctl}
                        invalid={Boolean(fieldErrors.mantis_project_id)}
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
                  {form.mantis_project_id && (
                    <p className={styles.note}>
                      Proyecto seleccionado: <strong>{form.mantis_project_name || form.mantis_project_id}</strong>
                    </p>
                  )}
                </>
              )}

              {!mantisProjects.length && !mantisLoadError && (
                <p className={styles.note}>
                  {form.mantis_protocol === "soap"
                    ? "Ingresá la URL, usuario y contraseña, luego hacé clic en \"Cargar proyectos\"."
                    : "Ingresá la URL y el token, luego hacé clic en \"Cargar proyectos\"."}
                </p>
              )}

              <details className={styles.advanced}>
                <summary>🔍 Opciones avanzadas Mantis</summary>
                <div className={styles.advancedBody}>
                  <Checkbox
                    labelClassName={styles.checkboxRow}
                    checked={form.verify_ssl === false}
                    onChange={(e) => patch("verify_ssl", !e.target.checked)}
                    label="Desactivar verificación SSL (redes corporativas con CA custom)"
                  />
                </div>
              </details>

              <p className={styles.note}>
                Las credenciales se guardan cifradas en <code>backend/projects/{"{nombre}"}/auth/mantis_auth.json</code>.
              </p>
            </div>
          )}

          <p className={styles.hint}>
            Se creará <code>backend/projects/{"{nombre}"}/config.json</code> con la configuración del proyecto.
          </p>

          {error && <div className={styles.error}>{error}</div>}
        </div>

        <div className={styles.footer}>
          <button className={styles.btnGhost} onClick={onClose} disabled={saving}>
            Cancelar
          </button>
          <button
            className={`${styles.btnAccent} ${pendingClass}`.trim()}
            onClick={handleSubmit}
            disabled={saving}
            aria-busy={saving || undefined}
          >
            {saving ? "Inicializando…" : "Crear e inicializar"}
          </button>
        </div>
      </div>
    </div>
  );
}
