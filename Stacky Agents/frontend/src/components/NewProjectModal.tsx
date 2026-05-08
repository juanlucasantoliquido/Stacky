import React, { useState } from "react";
import { Projects, Mantis, type MantisProject, type MantisListParams } from "../api/endpoints";
import type { InitProjectPayload, TrackerType } from "../types";
import styles from "./NewProjectModal.module.css";

interface Props {
  onClose: () => void;
  onCreated: (projectName: string, displayName: string) => void;
}

const EMPTY: InitProjectPayload = {
  name: "",
  display_name: "",
  workspace_root: "",
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
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Mantis: listar proyectos disponibles
  const [mantisProjects, setMantisProjects] = useState<MantisProject[]>([]);
  const [mantisLoading, setMantisLoading] = useState(false);
  const [mantisLoadError, setMantisLoadError] = useState<string | null>(null);

  function patch(key: keyof InitProjectPayload, value: unknown) {
    setForm((f) => ({ ...f, [key]: value }));
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

  async function handleSubmit() {
    setError(null);
    if (!form.name.trim()) { setError("Ingresá un nombre de proyecto"); return; }
    if (!form.workspace_root.trim()) { setError("Ingresá el workspace root"); return; }

    if (form.tracker_type === "azure_devops") {
      if (!form.organization?.trim()) { setError("Ingresá la organización de Azure DevOps"); return; }
      if (!form.ado_project?.trim()) { setError("Ingresá el proyecto de Azure DevOps"); return; }
    } else if (form.tracker_type === "jira") {
      if (!form.jira_url?.trim()) { setError("Ingresá la URL de Jira"); return; }
      if (!form.jira_key?.trim()) { setError("Ingresá la clave del proyecto Jira"); return; }
    } else {
      if (!form.mantis_url?.trim()) { setError("Ingresá la URL de Mantis"); return; }
      if (!form.mantis_project_id?.trim()) { setError("Selecci\u00f3n un proyecto de Mantis"); return; }
      const protocol = form.mantis_protocol || "rest";
      if (protocol === "soap") {
        if (!form.mantis_username?.trim()) { setError("Ingres\u00e1 el usuario de Mantis (SOAP)"); return; }
      } else {
        if (!form.mantis_token?.trim()) { setError("Ingres\u00e1 el token de API de Mantis"); return; }
      }
    }

    setSaving(true);
    try {
      const result = await Projects.init(form);
      if (result.ok) {
        onCreated(result.project.name, result.project.display_name);
        onClose();
      } else {
        setError((result as any).error || "Error desconocido");
      }
    } catch (e: any) {
      setError(e?.message || "Error de conexión");
    } finally {
      setSaving(false);
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
          <label className={styles.label}>Nombre interno del proyecto (ID, en mayúsculas)</label>
          <input
            className={styles.input}
            type="text"
            placeholder="Ej: RSPACIFICO, B2IMPACT"
            value={form.name}
            onChange={(e) => patch("name", e.target.value.toUpperCase())}
          />

          <label className={styles.label}>Nombre para mostrar</label>
          <input
            className={styles.input}
            type="text"
            placeholder="Ej: RS Pacífico"
            value={form.display_name ?? ""}
            onChange={(e) => patch("display_name", e.target.value)}
          />

          <label className={styles.label}>Workspace root (ruta al código fuente)</label>
          <input
            className={styles.input}
            type="text"
            placeholder="Ej: N:\GIT\RS\RSPacifico\trunk"
            value={form.workspace_root}
            onChange={(e) => patch("workspace_root", e.target.value)}
          />

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
              <label className={styles.label}>Organización ADO</label>
              <input
                className={styles.input}
                type="text"
                placeholder="Ej: UbimiaPacifico"
                value={form.organization ?? ""}
                onChange={(e) => patch("organization", e.target.value)}
              />
              <label className={styles.label}>Proyecto ADO</label>
              <input
                className={styles.input}
                type="text"
                placeholder="Ej: Strategist_Pacifico"
                value={form.ado_project ?? ""}
                onChange={(e) => patch("ado_project", e.target.value)}
              />
              <label className={styles.label}>Personal Access Token (PAT)</label>
              <input
                className={styles.input}
                type="password"
                placeholder="Pegá tu PAT de Azure DevOps"
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
                    placeholder="Ej: Strategist_Pacifico\AgendaWeb"
                    value={form.area_path ?? ""}
                    onChange={(e) => patch("area_path", e.target.value)}
                  />
                </div>
              </details>
            </div>
          )}

          {/* Campos Jira */}
          {isJira && (
            <div className={styles.trackerFields}>
              <span className={`${styles.trackerHeading} ${styles.trackerHeadingJira}`}>🔵 Jira</span>
              <label className={styles.label}>URL de la instancia Jira</label>
              <input
                className={styles.input}
                type="text"
                placeholder="Ej: https://empresa.atlassian.net  o  https://jira.intranet.com"
                value={form.jira_url ?? ""}
                onChange={(e) => patch("jira_url", e.target.value)}
              />
              <label className={styles.label}>Clave del proyecto (project key)</label>
              <input
                className={styles.input}
                type="text"
                placeholder="Ej: B2IM, PROJ, DEV"
                value={form.jira_key ?? ""}
                onChange={(e) => patch("jira_key", e.target.value)}
              />
              <label className={styles.label}>Usuario / Email</label>
              <input
                className={styles.input}
                type="text"
                placeholder="Ej: me@empresa.com"
                value={form.jira_user ?? ""}
                onChange={(e) => patch("jira_user", e.target.value)}
              />
              <label className={styles.label}>API Token</label>
              <input
                className={styles.input}
                type="password"
                placeholder="Pegá tu API token de Jira"
                value={form.jira_token ?? ""}
                onChange={(e) => patch("jira_token", e.target.value)}
              />
              <details className={styles.advanced}>
                <summary className={styles.advancedJira}>🔍 Opciones avanzadas Jira</summary>
                <div className={styles.advancedBody}>
                  <label className={styles.labelSm}>Versión API</label>
                  <select
                    className={styles.select}
                    value={form.api_version ?? "3"}
                    onChange={(e) => patch("api_version", e.target.value)}
                  >
                    <option value="3">v3 — Jira Cloud (*.atlassian.net)</option>
                    <option value="2">v2 — Jira Server / Data Center</option>
                  </select>
                  <label className={styles.labelSm}>JQL personalizado (opcional)</label>
                  <textarea
                    className={styles.textarea}
                    placeholder="Ej: assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
                    value={form.jql ?? ""}
                    onChange={(e) => patch("jql", e.target.value)}
                  />
                  <label className={styles.checkboxRow}>
                    <input
                      type="checkbox"
                      checked={form.verify_ssl === false}
                      onChange={(e) => patch("verify_ssl", !e.target.checked)}
                    />
                    Desactivar verificación SSL (redes corporativas con CA custom)
                  </label>
                </div>
              </details>
              <p className={styles.note}>
                Las credenciales se guardan en <code>backend/projects/{"{nombre}"}/auth/jira_auth.json</code>.
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
                    placeholder="Usuario de Mantis (ej: admin)"
                    value={form.mantis_username ?? ""}
                    onChange={(e) => patch("mantis_username", e.target.value)}
                  />
                  <label className={styles.label}>Contraseña</label>
                  <input
                    className={styles.input}
                    type="password"
                    placeholder="Contraseña de Mantis"
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
                    placeholder="Token de API de Mantis (Mi Cuenta → Tokens API)"
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
                  <label className={styles.checkboxRow}>
                    <input
                      type="checkbox"
                      checked={form.verify_ssl === false}
                      onChange={(e) => patch("verify_ssl", !e.target.checked)}
                    />
                    Desactivar verificación SSL (redes corporativas con CA custom)
                  </label>
                </div>
              </details>

              <p className={styles.note}>
                Las credenciales se guardan en <code>backend/projects/{"{nombre}"}/auth/mantis_auth.json</code>.
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
          <button className={styles.btnAccent} onClick={handleSubmit} disabled={saving}>
            {saving ? "Inicializando…" : "Crear e inicializar"}
          </button>
        </div>
      </div>
    </div>
  );
}
