/**
 * AgentConfigModal -- configuracion de roles por agente.
 *
 * Permite marcar tres flags por agente:
 *   - Stacky     -> disponible como empleado en el equipo
 *   - Utilitario -> disponible en el chat drawer de Stacky
 *   - VS Code    -> cuando utilitario+vscode, el chat se abre en VS Code;
 *                  solo vscode -> agente solo accesible desde VS Code
 *
 * Portado de WS2 (Sprint 3). Requiere AgentRoles en api/endpoints.ts y
 * GET /api/agent-roles en el backend (api/agent_roles.py).
 */
import { useEffect, useState } from "react";
import { AgentRoles, type AgentRoleEntry } from "../api/endpoints";
import { formatLoadErrorMessage } from "../utils/loadError";
import { Dialog } from "./ui";
import styles from "./AgentConfigModal.module.css";

interface Props {
  onClose: () => void;
}

type RolesMap = Record<string, AgentRoleEntry>;

const FLAG_META: {
  key: keyof Omit<AgentRoleEntry, "name" | "description">;
  label: string;
  title: string;
}[] = [
  { key: "stacky",     label: "Stacky",     title: "Disponible como empleado del equipo" },
  { key: "utilitario", label: "Utilitario", title: "Disponible en el chat drawer de Stacky" },
  { key: "vscode",     label: "VS Code",    title: "Se abre en VS Code (requiere Utilitario para chat, o solo para uso exclusivo en VS Code)" },
];

export default function AgentConfigModal({ onClose }: Props) {
  const [roles, setRoles] = useState<RolesMap>({});
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState<
    Record<string, Partial<Omit<AgentRoleEntry, "name" | "description">>>
  >({});
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    AgentRoles.list()
      .then((res) => setRoles(res.roles ?? {}))
      .catch(() => {
        setRoles({});
        setFetchError(true);
      })
      .finally(() => setLoading(false));
  }, []);

  function toggle(
    filename: string,
    key: keyof Omit<AgentRoleEntry, "name" | "description">
  ) {
    setRoles((prev) => {
      const current = prev[filename];
      if (!current) return prev;
      const updated = { ...current, [key]: !current[key] };
      return { ...prev, [filename]: updated };
    });
    setDirty((prev) => {
      const current = roles[filename];
      if (!current) return prev;
      return {
        ...prev,
        [filename]: {
          ...(prev[filename] ?? {}),
          [key]: !current[key],
        },
      };
    });
    setSaved(false);
  }

  async function handleSave() {
    if (!Object.keys(dirty).length) {
      onClose();
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await AgentRoles.update(dirty);
      setSaved(true);
      setDirty({});
      setTimeout(() => onClose(), 900);
    } catch (e) {
      // Plan 135 F7: el PUT falló — los cambios NO quedaron en el server (al
      // reabrir, el useEffect de carga los pisa). `dirty` se conserva (las
      // limpiezas están en el try, no corren ante throw) => reintento 1-click.
      setSaveError(formatLoadErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const filenames = Object.keys(roles).sort((a, b) =>
    (roles[a].name || a).localeCompare(roles[b].name || b)
  );

  return (
    <Dialog
      open
      onClose={onClose}
      closeGuard={{ dirty: Object.keys(dirty).length > 0, busy: saving }}
      ariaLabel="Configuracion de agentes"
      size="md"
    >
        <header className={styles.header}>
          <span className={styles.title}>Configuracion de agentes</span>
          <button className={styles.closeBtn} onClick={onClose} title="Cerrar">
            X
          </button>
        </header>

        <p className={styles.subtitle}>
          Configura el rol de cada agente detectado en VS Code.
        </p>

        {loading ? (
          <div className={styles.loadingRow}>Cargando agentes...</div>
        ) : fetchError ? (
          <div className={styles.errorRow}>
            No se pudo conectar con el backend.
            <br />
            <small>Reinicia el backend y vuelve a abrir este modal.</small>
          </div>
        ) : filenames.length === 0 ? (
          <div className={styles.loadingRow}>
            No se encontraron agentes en VS Code.
          </div>
        ) : (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.thName}>Agente</th>
                  {FLAG_META.map((f) => (
                    <th
                      key={f.key}
                      className={styles.thFlag}
                      title={f.title}
                    >
                      {f.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filenames.map((fn) => {
                  const entry = roles[fn];
                  return (
                    <tr key={fn} className={styles.row}>
                      <td className={styles.tdName}>
                        <span className={styles.agentName}>
                          {entry.name || fn}
                        </span>
                        {entry.description && (
                          <span className={styles.agentDesc}>
                            {entry.description}
                          </span>
                        )}
                      </td>
                      {FLAG_META.map((f) => (
                        <td key={f.key} className={styles.tdFlag}>
                          <label
                            className={styles.checkLabel}
                            title={f.title}
                          >
                            <input
                              type="checkbox"
                              checked={!!entry[f.key]}
                              onChange={() => toggle(fn, f.key)}
                              className={styles.checkbox}
                            />
                          </label>
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {saveError && (
          <div role="alert" className={styles.saveError}>
            No se pudo guardar: {saveError}. Tus cambios siguen en el formulario — reintentá con «Guardar».
          </div>
        )}
        <footer className={styles.footer}>
          <button
            className={styles.cancelBtn}
            onClick={onClose}
            disabled={saving}
          >
            Cancelar
          </button>
          <button
            className={`${styles.saveBtn}${saved ? " " + styles.saveBtnOk : ""}`}
            onClick={handleSave}
            disabled={saving || loading}
          >
            {saved ? "Guardado" : saving ? "Guardando..." : "Guardar"}
          </button>
        </footer>
    </Dialog>
  );
}
