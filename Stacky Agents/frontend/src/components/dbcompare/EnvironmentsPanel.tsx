import { useEffect, useState } from "react";
import { DbCompare } from "../../api/endpoints";
import type { DbEnvironment, TestConnectionResult } from "./dbcompareTypes";
import { validateEnvironmentForm, defaultPortFor, type EnvironmentFormValues } from "./envForm";
import { useConfirm } from "../ui";
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
  keyringAvailable: boolean;
}

export function EnvironmentsPanel({ keyringAvailable }: Props) {
  const askConfirm = useConfirm();
  const [environments, setEnvironments] = useState<DbEnvironment[]>([]);
  const [form, setForm] = useState<EnvironmentFormValues>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestConnectionResult>>({});
  const [passwordDraft, setPasswordDraft] = useState<Record<string, string>>({});

  const reload = () => {
    DbCompare.listEnvironments()
      .then((r) => setEnvironments(r.environments))
      .catch(() => setEnvironments([]));
  };

  useEffect(reload, []);

  const handleAdd = async () => {
    const { ok, errors } = validateEnvironmentForm(form);
    setFormErrors(errors);
    if (!ok) return;
    setFormError(null);
    const r = await DbCompare.upsertEnvironment({
      alias: form.alias,
      engine: form.engine,
      host: form.host,
      port: Number(form.port),
      database: form.database,
      username: form.username,
    });
    if (!r.ok) {
      setFormError(r.error || "No se pudo guardar el ambiente.");
      return;
    }
    setForm(EMPTY_FORM);
    reload();
  };

  const handleDelete = async (alias: string) => {
    if (!(await askConfirm({ title: 'Eliminar ambiente', message: `¿Eliminar el ambiente '${alias}'? Esto borra también su password guardada.`, tone: 'danger', confirmLabel: 'Eliminar' }))) return;
    await DbCompare.deleteEnvironment(alias);
    reload();
  };

  const handleTest = async (alias: string) => {
    const result = await DbCompare.testConnection(alias);
    setTestResults((prev) => ({ ...prev, [alias]: result }));
  };

  const handleSnapshot = async (alias: string) => {
    await DbCompare.takeSnapshot(alias);
    reload();
  };

  const handleSetPassword = async (alias: string) => {
    const password = passwordDraft[alias];
    if (!password) return;
    await DbCompare.setPassword(alias, password);
    setPasswordDraft((prev) => ({ ...prev, [alias]: "" }));
    reload();
  };

  return (
    <div className={styles.environmentsPanel}>
      <div className={styles.grid}>
        {environments.map((env) => {
          const result = testResults[env.alias];
          return (
            <div key={env.alias} className={styles.card}>
              <div className={styles.cardHeader}>
                <strong>{env.alias}</strong>
                <span className={styles.badge}>
                  {env.engine === "oracle" ? "Oracle" : env.engine === "sqlite" ? "SQLite" : "SQL Server"}
                </span>
              </div>
              <div className={styles.cardBody}>
                <div>{env.host}:{env.port} / {env.database}</div>
                <div>{env.has_password ? "🔑 con password" : "sin password"}</div>
                <div className={styles.recency}>
                  {env.latest_snapshot_taken_at
                    ? `Último snapshot: ${env.latest_snapshot_taken_at} (${env.latest_snapshot_hash8})`
                    : "Sin snapshot aún"}
                </div>
                {result && (
                  <div className={result.ok ? styles.testOk : styles.testFail}>
                    {result.ok
                      ? `OK — ${result.server_version || ""} (${result.latency_ms} ms)`
                      : `Error: ${result.error}${result.likely_network ? " (probable problema de red/VPN, no necesariamente credencial incorrecta)" : ""}`}
                  </div>
                )}
                <div className={styles.passwordRow}>
                  <input
                    type="password"
                    placeholder="Password (solo lectura)"
                    value={passwordDraft[env.alias] || ""}
                    onChange={(e) => setPasswordDraft((prev) => ({ ...prev, [env.alias]: e.target.value }))}
                  />
                  <button onClick={() => handleSetPassword(env.alias)} disabled={!keyringAvailable}>
                    Guardar password
                  </button>
                </div>
              </div>
              <div className={styles.cardActions}>
                <button onClick={() => handleTest(env.alias)}>Probar conexión</button>
                <button onClick={() => handleSnapshot(env.alias)}>Snapshot</button>
                <button onClick={() => handleDelete(env.alias)} className={styles.dangerButton}>
                  Eliminar
                </button>
              </div>
            </div>
          );
        })}
        {environments.length === 0 && (
          <div className={styles.emptyState}>Todavía no registraste ningún ambiente.</div>
        )}
      </div>

      <div className={styles.form}>
        <h3>Registrar ambiente</h3>
        <div className={styles.formGrid}>
          <label>
            Alias
            <input
              value={form.alias}
              onChange={(e) => setForm({ ...form, alias: e.target.value })}
              placeholder="PACIFICO-DEV"
            />
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
            <input
              type="number"
              value={form.port}
              onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}
            />
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
        </div>
        <p className={styles.readonlyNote}>
          Usá una credencial de SOLO LECTURA: Stacky solo lee catálogo y datos, jamás escribe.
        </p>
        {formError && <div className={styles.fieldError}>{formError}</div>}
        <button onClick={handleAdd}>Agregar ambiente</button>
      </div>
    </div>
  );
}

export default EnvironmentsPanel;
