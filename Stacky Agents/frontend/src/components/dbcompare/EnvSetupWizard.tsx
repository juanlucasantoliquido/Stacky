// Plan 157 F4 — wizard guiado de alta de ambientes en contexto.
// 3 modos: (A) pegar datasource, (B) desde web.config, (C) manual.
// HITL: autodetectar muestra un PREVIEW editable; el operador confirma. La password
// detectada NUNCA viaja al browser: viaja el flag has_password; el confirm la toma
// del cache de proceso y la escribe a keyring.
// Rieles: sin diálogos nativos del navegador (ratchet 156) y sin estilos inline
// literales (ratchet 138); confirmaciones = acción explícita de botón (HITL).
import { useState, type ChangeEvent } from "react";
import { DbCompare } from "../../api/endpoints";
import { DbCompareImport } from "./importConfigApi";
import { validateEnvironmentForm, defaultPortFor, type EnvironmentFormValues } from "./envForm";
import {
  availableModes,
  chooseInitialMode,
  mapPreviewToForm,
  type ImportPreview,
  type SetupMode,
} from "./envSetupLogic";
import { CredentialWarningBanner } from "./CredentialWarningBanner";
import styles from "./dbcompare.module.css";

const EMPTY_FORM: EnvironmentFormValues = {
  alias: "",
  engine: "sqlserver",
  host: "",
  port: 1433,
  database: "",
  username: "",
};

interface Props {
  webconfigImportEnabled: boolean;
  onCreated: () => void;
  onCancel: () => void;
}

const MODE_LABEL: Record<SetupMode, string> = {
  datasource: "Pegar datasource",
  webconfig: "Desde web.config",
  manual: "Manual (avanzado)",
};

export function EnvSetupWizard({ webconfigImportEnabled, onCreated, onCancel }: Props) {
  const flags = { webconfigImportEnabled };
  const modes = availableModes(flags);
  const [mode, setMode] = useState<SetupMode>(chooseInitialMode(flags));

  const [rawDatasource, setRawDatasource] = useState("");
  const [connections, setConnections] = useState<ImportPreview[]>([]);
  const [importId, setImportId] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const [form, setForm] = useState<EnvironmentFormValues>(EMPTY_FORM);
  const [password, setPassword] = useState("");
  const [hasDetectedPassword, setHasDetectedPassword] = useState(false);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const resetDetection = () => {
    setConnections([]);
    setImportId(null);
    setSelectedIndex(null);
    setShowForm(false);
    setHasDetectedPassword(false);
    setPassword("");
    setError(null);
  };

  const selectMode = (m: SetupMode) => {
    setMode(m);
    resetDetection();
    if (m === "manual") {
      setForm(EMPTY_FORM);
      setShowForm(true);
    } else {
      setForm(EMPTY_FORM);
      setShowForm(false);
    }
  };

  const applyPreview = (preview: ImportPreview, newImportId: string) => {
    setForm(mapPreviewToForm(preview));
    setImportId(newImportId);
    setSelectedIndex(preview.index);
    setHasDetectedPassword(preview.has_password);
    setPassword("");
    setShowForm(true);
  };

  const detect = async (payload: { content?: string; path?: string }) => {
    setBusy(true);
    setError(null);
    try {
      const r = await DbCompareImport.importConfig(payload);
      if (!r.ok || !r.import_id || !r.connections || r.connections.length === 0) {
        setError(r.error || "No se detectó ninguna conexión en el contenido provisto.");
        return;
      }
      setConnections(r.connections);
      setImportId(r.import_id);
      if (r.connections.length === 1) {
        applyPreview(r.connections[0], r.import_id);
      }
    } catch {
      setError("Error al detectar conexiones (revisá el archivo/datasource).");
    } finally {
      setBusy(false);
    }
  };

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => detect({ content: String(reader.result || "") });
    reader.readAsText(file);
  };

  const save = async () => {
    const { ok, errors } = validateEnvironmentForm(form);
    setFormErrors(errors);
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      if (importId != null && selectedIndex != null) {
        const r = await DbCompareImport.confirmImport({
          import_id: importId,
          index: selectedIndex,
          alias: form.alias,
          overrides: {
            engine: form.engine,
            host: form.host,
            port: Number(form.port),
            database: form.database,
            username: form.username,
          },
        });
        if (!r.ok) {
          setError(r.error || "No se pudo crear el ambiente.");
          return;
        }
        if (password) await DbCompare.setPassword(form.alias, password);
      } else {
        const r = await DbCompare.upsertEnvironment({
          alias: form.alias,
          engine: form.engine,
          host: form.host,
          port: Number(form.port),
          database: form.database,
          username: form.username,
        });
        if (!r.ok) {
          setError(r.error || "No se pudo crear el ambiente.");
          return;
        }
        if (password) await DbCompare.setPassword(form.alias, password);
      }
      onCreated();
    } catch {
      setError("Error al guardar el ambiente.");
    } finally {
      setBusy(false);
    }
  };

  const showBanner = mode !== "manual" || hasDetectedPassword;

  return (
    <div className={styles.form}>
      <h3>Agregar una base de datos</h3>

      <div className={styles.wizardModes}>
        {modes.map((m) => (
          <button key={m} onClick={() => selectMode(m)} aria-pressed={mode === m}>
            {MODE_LABEL[m]}
          </button>
        ))}
      </div>

      {mode === "datasource" && (
        <div>
          <label>
            Pegá tu datasource / connection string
            <textarea
              className={styles.wizardTextarea}
              value={rawDatasource}
              onChange={(e) => setRawDatasource(e.target.value)}
              placeholder="Server=host,1433;Database=RS;User ID=u;Password=..."
            />
          </label>
          <div className={styles.wizardActions}>
            <button onClick={() => detect({ content: rawDatasource })} disabled={busy || !rawDatasource.trim()}>
              Detectar
            </button>
          </div>
        </div>
      )}

      {mode === "webconfig" && (
        <div>
          <label>
            Elegí un archivo web.config / XMLConfig
            <input type="file" accept=".config,.xml" onChange={onFile} />
          </label>
          {connections.length > 1 && (
            <div>
              <p className={styles.subtitle}>Elegí la conexión a importar:</p>
              {connections.map((c) => (
                <label key={c.index} className={styles.connectionOption}>
                  <input
                    type="radio"
                    name="conn"
                    checked={selectedIndex === c.index}
                    onChange={() => importId && applyPreview(c, importId)}
                  />{" "}
                  <strong>{c.name || `Conexión ${c.index + 1}`}</strong> — {c.engine || "engine?"} · {c.host}
                  {c.port ? `:${c.port}` : ""} / {c.database} {c.has_password ? "🔑" : ""}
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {showBanner && <CredentialWarningBanner />}

      {showForm && (
        <div className={styles.formGrid}>
          <label>
            Alias
            <input value={form.alias} onChange={(e) => setForm({ ...form, alias: e.target.value })} placeholder="PACIFICO-DEV" />
            {formErrors.alias && <span className={styles.fieldError}>{formErrors.alias}</span>}
          </label>
          <label>
            Motor
            <select
              value={form.engine}
              onChange={(e) => setForm({ ...form, engine: e.target.value, port: defaultPortFor(e.target.value) })}
            >
              <option value="sqlserver">SQL Server</option>
              <option value="oracle">Oracle</option>
            </select>
            {formErrors.engine && <span className={styles.fieldError}>{formErrors.engine}</span>}
          </label>
          <label>
            Host
            <input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} />
            {formErrors.host && <span className={styles.fieldError}>{formErrors.host}</span>}
          </label>
          <label>
            Puerto
            <input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} />
            {formErrors.port && <span className={styles.fieldError}>{formErrors.port}</span>}
          </label>
          <label>
            Database
            <input value={form.database} onChange={(e) => setForm({ ...form, database: e.target.value })} />
            {formErrors.database && <span className={styles.fieldError}>{formErrors.database}</span>}
          </label>
          <label>
            Username
            <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            {formErrors.username && <span className={styles.fieldError}>{formErrors.username}</span>}
          </label>
          <label>
            Password {hasDetectedPassword ? "(detectada — se guardará cifrada; dejala vacía para usar la detectada)" : ""}
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={hasDetectedPassword ? "••••" : "Password (solo lectura)"}
            />
          </label>
        </div>
      )}

      {showForm && (
        <p className={styles.readonlyNote}>
          Usá una credencial de SOLO LECTURA: Stacky solo lee catálogo y datos, jamás escribe.
        </p>
      )}

      {error && <div className={styles.fieldError}>{error}</div>}

      <div className={styles.wizardActions}>
        {showForm && (
          <button onClick={save} disabled={busy}>
            Guardar
          </button>
        )}
        <button onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
    </div>
  );
}

export default EnvSetupWizard;
