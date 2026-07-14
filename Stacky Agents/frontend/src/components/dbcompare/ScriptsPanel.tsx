import { useEffect, useState } from "react";
import { DbCompare } from "../../api/endpoints";
import { buildScriptRows, pairingBadge, type Manifest, type ScriptPairRow } from "./scriptsLogic";
import { SqlViewer } from "./SqlViewer";
import styles from "./dbcompare.module.css";

interface Props {
  runId: string;
}

const PAIRING_LABEL: Record<ReturnType<typeof pairingBadge>, string> = {
  backup: "backup",
  rollback: "rollback",
  "backup+rollback": "backup+rollback",
  "sin resguardo (aditivo)": "sin resguardo (aditivo)",
};

/**
 * ScriptsPanel — Plan 125 F6. Tab "Scripts" del Comparador de BD: genera y
 * muestra el bundle de scripts de paridad + backups pareados 1:1 de un run
 * `done`. Stacky GENERA; el operador ejecuta en su propia herramienta
 * (SSMS/SQL Developer) — banner HITL siempre visible, sin excepción.
 */
export function ScriptsPanel({ runId }: Props) {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewingRow, setViewingRow] = useState<ScriptPairRow | null>(null);

  const reload = () => {
    DbCompare.getManifest(runId)
      .then((r) => setManifest(r.ok ? r.manifest ?? null : null))
      .catch(() => setManifest(null));
  };

  useEffect(reload, [runId]);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await DbCompare.generateScripts(runId);
      if (!r.ok || !r.manifest) {
        setError(r.error || "No se pudieron generar los scripts.");
        return;
      }
      setManifest(r.manifest);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  if (!manifest) {
    return (
      <div className={styles.scriptsPanel}>
        {error && <div className={styles.fieldError}>{error}</div>}
        <button onClick={handleGenerate} disabled={loading}>
          {loading ? "Generando..." : "Generar scripts de paridad + backups"}
        </button>
      </div>
    );
  }

  const rows = buildScriptRows(manifest);

  return (
    <div className={styles.scriptsPanel}>
      <div className={styles.hitlBanner}>
        🛑 Stacky genera; VOS ejecutás. Orden: 1) backups → 2) paridad → 3) destructivos (revisados).
      </div>

      <table className={styles.scriptsTable}>
        <thead>
          <tr>
            <th>Seq</th>
            <th>Objeto</th>
            <th>Acción</th>
            <th>Pareo</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.file}>
              <td>{row.seq}</td>
              <td>{row.objectLabel}</td>
              <td>
                {row.action}
                {row.destructive && <span className={styles.destructiveChip}>DESTRUCTIVO</span>}
              </td>
              <td>
                <span className={styles.badge}>{PAIRING_LABEL[pairingBadge(row)]}</span>
              </td>
              <td className={styles.scriptsRowActions}>
                <button onClick={() => setViewingRow(row)}>Ver</button>
                <a href={DbCompare.scriptFileUrl(runId, row.file)} download={row.file.split("/").pop()}>
                  Descargar
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className={styles.scriptsFooter}>
        <span>
          {manifest.counts.backups} backups · {manifest.counts.parity} paridad · {manifest.counts.destructive}{" "}
          destructivos
        </span>
        <button onClick={() => DbCompare.downloadScriptsZip(runId)}>Descargar TODO (.zip)</button>
      </div>

      {viewingRow && <SqlViewer runId={runId} row={viewingRow} onClose={() => setViewingRow(null)} />}
    </div>
  );
}

export default ScriptsPanel;
