import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ClientProfileApi,
  DbReadonlyAuth,
  type ClientProfile,
} from "../api/endpoints";
import { useWorkbench } from "../store/workbench";

const box: React.CSSProperties = {
  background: "#11161d",
  border: "1px solid #1f2a37",
  borderRadius: 8,
  padding: 16,
  marginBottom: 16,
};
const btn: React.CSSProperties = {
  background: "#2563eb",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  padding: "8px 14px",
  cursor: "pointer",
  fontSize: 13,
};
const btnGhost: React.CSSProperties = {
  ...btn,
  background: "transparent",
  border: "1px solid #334155",
};
const textarea: React.CSSProperties = {
  width: "100%",
  minHeight: 360,
  background: "#0a0e14",
  color: "#cbd5e1",
  border: "1px solid #1f2a37",
  borderRadius: 6,
  padding: 12,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  fontSize: 13,
  lineHeight: 1.5,
};
const label: React.CSSProperties = {
  display: "block",
  marginBottom: 4,
  color: "#94a3b8",
  fontSize: 12,
};
const input: React.CSSProperties = {
  width: "100%",
  background: "#0a0e14",
  color: "#cbd5e1",
  border: "1px solid #1f2a37",
  borderRadius: 6,
  padding: "8px 10px",
  fontSize: 13,
};

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "{}";
  }
}

export default function ClientProfileEditor() {
  const qc = useQueryClient();
  const activeProject = useWorkbench((s) => s.activeProject);
  const projectName = activeProject?.name ?? null;

  const profileQuery = useQuery({
    queryKey: ["client-profile", projectName],
    queryFn: () => ClientProfileApi.get(projectName!),
    enabled: !!projectName,
  });

  const dbAuthQuery = useQuery({
    queryKey: ["client-profile", "db-auth", projectName],
    queryFn: () => DbReadonlyAuth.meta(projectName!),
    enabled: !!projectName,
  });

  const [draft, setDraft] = useState<string>("");
  const [parseError, setParseError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);

  const [dbServer, setDbServer] = useState("");
  const [dbDatabase, setDbDatabase] = useState("");
  const [dbUser, setDbUser] = useState("");
  const [dbPassword, setDbPassword] = useState("");
  const [dbBusy, setDbBusy] = useState(false);
  const [dbNotice, setDbNotice] = useState<string | null>(null);
  const [dbError, setDbError] = useState<string | null>(null);

  useEffect(() => {
    if (!profileQuery.data) return;
    const initial = profileQuery.data.has_profile
      ? profileQuery.data.profile
      : profileQuery.data.default_template;
    setDraft(safeStringify(initial ?? {}));
    setWarnings(profileQuery.data.validation?.warnings ?? []);
  }, [profileQuery.data]);

  useEffect(() => {
    if (!dbAuthQuery.data) return;
    setDbServer(dbAuthQuery.data.server ?? "");
    setDbDatabase(dbAuthQuery.data.database ?? "");
    setDbUser(dbAuthQuery.data.user ?? "");
  }, [dbAuthQuery.data]);

  const parsed = useMemo<ClientProfile | null>(() => {
    if (!draft.trim()) {
      setParseError("El JSON está vacío.");
      return null;
    }
    try {
      const obj = JSON.parse(draft);
      if (typeof obj !== "object" || obj === null || Array.isArray(obj)) {
        setParseError("El JSON raíz debe ser un objeto.");
        return null;
      }
      setParseError(null);
      return obj as ClientProfile;
    } catch (err) {
      setParseError(err instanceof Error ? err.message : "JSON inválido");
      return null;
    }
  }, [draft]);

  if (!projectName) {
    return (
      <div style={box}>
        <p style={{ color: "#cbd5e1" }}>Seleccioná un proyecto activo para editar su perfil de cliente.</p>
      </div>
    );
  }

  if (profileQuery.isLoading) {
    return (
      <div style={box}>
        <p style={{ color: "#94a3b8" }}>Cargando perfil del cliente…</p>
      </div>
    );
  }

  if (profileQuery.error) {
    return (
      <div style={box}>
        <p style={{ color: "#f87171" }}>Error: {String(profileQuery.error)}</p>
      </div>
    );
  }

  const trackerType = profileQuery.data?.tracker_type ?? "azure_devops";
  const hasProfile = !!profileQuery.data?.has_profile;

  const onApplyDefault = () => {
    if (profileQuery.data?.default_template) {
      setDraft(safeStringify(profileQuery.data.default_template));
      setSaveNotice(`Template default del tracker '${trackerType}' aplicado al editor (no se guardó todavía).`);
      setSaveError(null);
    }
  };

  const onSave = async () => {
    if (!parsed) {
      setSaveError("Corregí el JSON antes de guardar.");
      return;
    }
    setBusy(true);
    setSaveError(null);
    setSaveNotice(null);
    try {
      const res = await ClientProfileApi.save(projectName, parsed);
      if (!res.ok) {
        setSaveError(res.error ?? "Error desconocido al guardar.");
      } else {
        setSaveNotice("Perfil guardado correctamente.");
        setWarnings(res.warnings ?? []);
        await qc.invalidateQueries({ queryKey: ["client-profile", projectName] });
        await qc.invalidateQueries({ queryKey: ["projects"] });
      }
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error al guardar.");
    } finally {
      setBusy(false);
    }
  };

  const onClear = async () => {
    if (!confirm("¿Eliminar el client_profile del proyecto? Los agentes genéricos volverán al fallback (preguntar al operador).")) {
      return;
    }
    setBusy(true);
    setSaveError(null);
    setSaveNotice(null);
    try {
      const res = await ClientProfileApi.clear(projectName);
      if (res.ok) {
        setSaveNotice("Perfil eliminado.");
        await qc.invalidateQueries({ queryKey: ["client-profile", projectName] });
        await qc.invalidateQueries({ queryKey: ["projects"] });
      } else {
        setSaveError(res.error ?? "No se pudo eliminar.");
      }
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error al eliminar.");
    } finally {
      setBusy(false);
    }
  };

  const onSaveDbAuth = async () => {
    if (!dbPassword.trim()) {
      setDbError("Password requerido.");
      return;
    }
    setDbBusy(true);
    setDbError(null);
    setDbNotice(null);
    try {
      const res = await DbReadonlyAuth.save(projectName, {
        server: dbServer.trim() || undefined,
        database: dbDatabase.trim() || undefined,
        user: dbUser.trim() || undefined,
        password: dbPassword,
      });
      if (res.ok) {
        setDbNotice("Credencial BD readonly guardada.");
        setDbPassword("");
        await qc.invalidateQueries({ queryKey: ["client-profile", "db-auth", projectName] });
      } else {
        setDbError(res.error ?? "Error al guardar la credencial.");
      }
    } catch (err) {
      setDbError(err instanceof Error ? err.message : "Error al guardar.");
    } finally {
      setDbBusy(false);
    }
  };

  return (
    <div>
      <div style={box}>
        <h3 style={{ marginTop: 0, color: "#e2e8f0" }}>Perfil del cliente — {projectName}</h3>
        <p style={{ color: "#94a3b8", fontSize: 13 }}>
          Datos específicos del cliente que los agentes genéricos consumen sin
          hardcodearlos. El bloque <code>client-profile</code> se inyecta como
          context block en cada ejecución de agente (sin secretos).
        </p>
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12 }}>
          <span style={{ color: "#94a3b8", fontSize: 13 }}>
            Tracker: <strong style={{ color: "#cbd5e1" }}>{trackerType}</strong>
          </span>
          <span style={{ color: "#94a3b8", fontSize: 13 }}>
            Estado: {hasProfile ? <strong style={{ color: "#10b981" }}>Configurado</strong> : <strong style={{ color: "#f59e0b" }}>Sin configurar</strong>}
          </span>
          <span style={{ flex: 1 }} />
          <button style={btnGhost} onClick={onApplyDefault} disabled={busy}>
            Aplicar template default ({trackerType})
          </button>
          {hasProfile && (
            <button style={{ ...btnGhost, borderColor: "#f87171", color: "#f87171" }} onClick={onClear} disabled={busy}>
              Eliminar perfil
            </button>
          )}
        </div>

        <textarea
          style={textarea}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          spellCheck={false}
          aria-label="Editor JSON del client_profile"
        />

        {parseError && <div style={{ color: "#f87171", marginTop: 8, fontSize: 13 }}>JSON: {parseError}</div>}

        {warnings.length > 0 && (
          <div style={{ marginTop: 12, padding: 10, background: "#1e1b00", border: "1px solid #facc15", borderRadius: 6 }}>
            <strong style={{ color: "#facc15" }}>Advertencias del validador:</strong>
            <ul style={{ margin: "6px 0 0 18px", color: "#fde68a", fontSize: 13 }}>
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        )}

        {saveError && <div style={{ color: "#f87171", marginTop: 8 }}>{saveError}</div>}
        {saveNotice && <div style={{ color: "#10b981", marginTop: 8 }}>{saveNotice}</div>}

        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button style={btn} onClick={onSave} disabled={busy || !!parseError}>
            {busy ? "Guardando…" : "Guardar perfil"}
          </button>
        </div>
      </div>

      <div style={box}>
        <h3 style={{ marginTop: 0, color: "#e2e8f0" }}>Credencial BD readonly</h3>
        <p style={{ color: "#94a3b8", fontSize: 13 }}>
          La credencial se cifra con DPAPI y se guarda en{" "}
          <code>backend/projects/{projectName}/auth/db_readonly.json</code>. El
          password nunca viaja al LLM ni queda en el client_profile.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <label style={label}>Server</label>
            <input style={input} value={dbServer} onChange={(e) => setDbServer(e.target.value)} placeholder="aisbddev02.cloud.ais-int.net" />
          </div>
          <div>
            <label style={label}>Base de datos (opcional)</label>
            <input style={input} value={dbDatabase} onChange={(e) => setDbDatabase(e.target.value)} placeholder="Pacifico" />
          </div>
          <div>
            <label style={label}>Usuario readonly</label>
            <input style={input} value={dbUser} onChange={(e) => setDbUser(e.target.value)} placeholder="RSPACIFICOREAD" />
          </div>
          <div>
            <label style={label}>Password</label>
            <input
              style={input}
              type="password"
              value={dbPassword}
              onChange={(e) => setDbPassword(e.target.value)}
              placeholder={dbAuthQuery.data?.has_credentials ? "(ya guardado — dejar vacío si no querés cambiarlo)" : ""}
            />
          </div>
        </div>

        {dbError && <div style={{ color: "#f87171", marginTop: 8 }}>{dbError}</div>}
        {dbNotice && <div style={{ color: "#10b981", marginTop: 8 }}>{dbNotice}</div>}

        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button style={btn} onClick={onSaveDbAuth} disabled={dbBusy}>
            {dbBusy ? "Guardando…" : (dbAuthQuery.data?.has_credentials ? "Actualizar credencial" : "Guardar credencial")}
          </button>
        </div>
      </div>
    </div>
  );
}
