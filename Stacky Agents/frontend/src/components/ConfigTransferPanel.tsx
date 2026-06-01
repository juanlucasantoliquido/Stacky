import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ConfigTransfer,
  type ConfigBundle,
  type ConfigImportResult,
} from "../api/endpoints";
import { useWorkbench } from "../store/workbench";

type ImportMode = "merge" | "overwrite";

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

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

function isAllProjectsBundle(bundle: ConfigBundle | null): boolean {
  if (!bundle) return false;
  return bundle.meta?.scope === "allProjects" || Array.isArray(bundle.projects);
}

export default function ConfigTransferPanel() {
  const qc = useQueryClient();
  const activeProject = useWorkbench((s) => s.activeProject);
  const projectName = activeProject?.name ?? null;

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingBundle, setPendingBundle] = useState<ConfigBundle | null>(null);
  const [dryRun, setDryRun] = useState<ConfigImportResult | null>(null);
  const [importMode, setImportMode] = useState<ImportMode>("merge");
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: eventsData } = useQuery({
    queryKey: ["config-transfer-events", projectName],
    queryFn: () => ConfigTransfer.events(projectName as string, 20),
    enabled: !!projectName,
    staleTime: 30_000,
  });

  const reset = () => {
    setPendingBundle(null);
    setDryRun(null);
    setError(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleExport = useCallback(async () => {
    if (!projectName) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await ConfigTransfer.export(projectName);
      if (!res.ok) throw new Error(res.error || "Falló la exportación");
      downloadJson(res.filename, res.bundle);
      setNotice(`Configuración exportada: ${res.filename}`);
      qc.invalidateQueries({ queryKey: ["config-transfer-events", projectName] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al exportar");
    } finally {
      setBusy(false);
    }
  }, [projectName, qc]);

  const handleExportAll = useCallback(async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await ConfigTransfer.exportAll();
      if (!res.ok) throw new Error(res.error || "Falló la exportación");
      downloadJson(res.filename, res.bundle);
      const count = res.bundle.meta?.projectCount ?? (Array.isArray(res.bundle.projects) ? res.bundle.projects.length : 0);
      setNotice(`Configuración completa exportada: ${res.filename} (${count} proyecto(s))`);
      if (projectName) qc.invalidateQueries({ queryKey: ["config-transfer-events", projectName] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al exportar");
    } finally {
      setBusy(false);
    }
  }, [projectName, qc]);

  const handleFile = useCallback(
    async (file: File) => {
      setBusy(true);
      setError(null);
      setNotice(null);
      setDryRun(null);
      try {
        const text = await file.text();
        const bundle = JSON.parse(text) as ConfigBundle;
        const allProjects = isAllProjectsBundle(bundle);
        if (!allProjects && !projectName) {
          throw new Error("Seleccioná un proyecto activo para importar un bundle de un solo proyecto.");
        }
        setPendingBundle(bundle);
        const result = allProjects
          ? await ConfigTransfer.importAll(bundle, "dry-run")
          : await ConfigTransfer.import(projectName as string, bundle, "dry-run");
        setDryRun(result);
        if (!result.ok) {
          setError(
            result.validation?.errors?.join(" · ") || result.error || "El archivo no es válido"
          );
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "No se pudo leer el archivo JSON");
        setPendingBundle(null);
      } finally {
        setBusy(false);
      }
    },
    [projectName]
  );

  const handleApply = useCallback(async () => {
    if (!pendingBundle) return;
    const allProjects = isAllProjectsBundle(pendingBundle);
    if (!allProjects && !projectName) return;
    setBusy(true);
    setError(null);
    try {
      const result = allProjects
        ? await ConfigTransfer.importAll(pendingBundle, importMode)
        : await ConfigTransfer.import(projectName as string, pendingBundle, importMode);
      if (!result.ok) {
        setError(result.validation?.errors?.join(" · ") || result.error || "Falló la importación");
        return;
      }
      const n = result.changes?.length ?? 0;
      const projectCount = result.projects?.length ?? 1;
      setNotice(
        result.idempotent
          ? "Sin cambios: la configuración ya estaba aplicada (idempotente)."
          : `Importación aplicada (${importMode}): ${n} cambio(s) en ${projectCount} proyecto(s).`
      );
      reset();
      if (projectName) qc.invalidateQueries({ queryKey: ["config-transfer-events", projectName] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["active-project"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al importar");
    } finally {
      setBusy(false);
    }
  }, [projectName, pendingBundle, importMode, qc]);

  const changes = dryRun?.changes ?? [];
  const secretsRequired = dryRun?.secrets_required ?? [];
  const canApply = !!dryRun?.ok && !!pendingBundle;

  return (
    <div>
      {notice && (
        <div style={{ ...box, borderColor: "#16a34a", color: "#86efac" }}>{notice}</div>
      )}
      {error && (
        <div style={{ ...box, borderColor: "#b91c1c", color: "#fca5a5" }} role="alert">
          {error}
        </div>
      )}

      {/* Exportar */}
      <div style={box}>
        <h3 style={{ margin: "0 0 6px", color: "#e2e8f0" }}>Exportar configuración</h3>
        <p style={{ color: "#94a3b8", fontSize: 13, marginTop: 0 }}>
          Descarga un archivo versionado con la configuración de Stacky Agents. Podés exportar
          sólo el proyecto activo o todos los proyectos para restaurar una instalación desde cero.
          Los secretos (PAT/tokens) <strong>no</strong> se exportan: el archivo solo registra qué
          credenciales habrá que volver a cargar.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button style={btn} onClick={handleExportAll} disabled={busy}>
            {busy ? "…" : "⬇ Exportar todos los proyectos"}
          </button>
          <button style={btnGhost} onClick={handleExport} disabled={busy || !projectName}>
            {projectName ? "Exportar proyecto activo" : "Sin proyecto activo"}
          </button>
        </div>
      </div>

      {/* Importar */}
      <div style={box}>
        <h3 style={{ margin: "0 0 6px", color: "#e2e8f0" }}>Importar configuración</h3>
        <p style={{ color: "#94a3b8", fontSize: 13, marginTop: 0 }}>
          Subí un archivo exportado para previsualizar los cambios (dry-run) antes de aplicarlos.
          Si el archivo contiene todos los proyectos, se crearán los que falten.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
          style={{ color: "#cbd5e1", fontSize: 13 }}
        />

        {dryRun && (
          <div style={{ marginTop: 14 }}>
            {dryRun.validation && (
              <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 8 }}>
                Schema v{dryRun.validation.schema_version ?? "?"} ·{" "}
                {dryRun.validation.app_version ?? "?"} ·{" "}
                checksum {dryRun.validation.checksum_ok ? "✔ válido" : "—"}
                {dryRun.validation.warnings?.map((w, i) => (
                  <div key={i} style={{ color: "#fbbf24" }}>⚠ {w}</div>
                ))}
              </div>
            )}

            <div style={{ fontWeight: 600, color: "#e2e8f0", marginBottom: 6 }}>
              {changes.length === 0
                ? "Sin cambios: la configuración del destino ya coincide (idempotente)."
                : `${changes.length} cambio(s) a aplicar:`}
            </div>
            {dryRun.projects && dryRun.projects.length > 0 && (
              <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 8 }}>
                Proyectos incluidos: {dryRun.projects.map((p) => p.project).join(", ")}
              </div>
            )}
            {changes.length > 0 && (
              <div
                style={{
                  maxHeight: 240,
                  overflow: "auto",
                  border: "1px solid #1f2a37",
                  borderRadius: 6,
                }}
              >
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: "#0b1015", color: "#94a3b8", textAlign: "left" }}>
                      <th style={{ padding: "6px 8px" }}>Sección</th>
                      <th style={{ padding: "6px 8px" }}>Campo</th>
                      <th style={{ padding: "6px 8px" }}>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {changes.map((c, i) => (
                      <tr key={i} style={{ borderTop: "1px solid #1f2a37", color: "#cbd5e1" }}>
                        <td style={{ padding: "6px 8px" }}>{c.section}</td>
                        <td style={{ padding: "6px 8px", fontFamily: "monospace" }}>{c.field}</td>
                        <td
                          style={{
                            padding: "6px 8px",
                            color:
                              c.action === "add"
                                ? "#86efac"
                                : c.action === "remove"
                                ? "#fca5a5"
                                : "#7dd3fc",
                          }}
                        >
                          {c.action}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {secretsRequired.length > 0 && (
              <div style={{ marginTop: 10, color: "#fbbf24", fontSize: 12 }}>
                🔐 Credenciales a re-cargar tras importar:
                <ul style={{ margin: "4px 0 0 18px" }}>
                  {secretsRequired.map((s, i) => (
                    <li key={i}>
                      {s.tracker_type} — {s.auth_file} ({(s.fields || []).join(", ") || "—"})
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {canApply && (
              <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 10 }}>
                <label style={{ color: "#cbd5e1", fontSize: 13 }}>
                  Modo:&nbsp;
                  <select
                    value={importMode}
                    onChange={(e) => setImportMode(e.target.value as ImportMode)}
                    style={{ background: "#0b1015", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 4, padding: "4px 8px" }}
                  >
                    <option value="merge">Merge (fusionar, no pisa con vacío)</option>
                    <option value="overwrite">Overwrite (reemplazar por sección)</option>
                  </select>
                </label>
                <button style={btn} onClick={handleApply} disabled={busy}>
                  {busy ? "Aplicando…" : "✔ Aplicar importación"}
                </button>
                <button style={btnGhost} onClick={reset} disabled={busy}>
                  Cancelar
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Auditoría */}
      {eventsData?.events && eventsData.events.length > 0 && (
        <div style={box}>
          <h3 style={{ margin: "0 0 8px", color: "#e2e8f0" }}>Historial de transferencias</h3>
          <div style={{ maxHeight: 200, overflow: "auto" }}>
            {eventsData.events.map((ev, i) => (
              <div
                key={i}
                style={{
                  fontSize: 12,
                  color: "#94a3b8",
                  padding: "4px 0",
                  borderTop: i ? "1px solid #1f2a37" : "none",
                }}
              >
                <span style={{ color: "#7dd3fc" }}>{ev.action}</span>
                {ev.mode ? ` (${ev.mode})` : ""} · {ev.result} · {ev.ts}
                {ev.actor ? ` · ${ev.actor}` : ""}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
