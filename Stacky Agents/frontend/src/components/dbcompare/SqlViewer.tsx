import { useEffect, useState } from "react";
import { DbCompare } from "../../api/endpoints";
import type { ScriptPairRow } from "./scriptsLogic";
import styles from "./dbcompare.module.css";

interface Props {
  runId: string;
  row: ScriptPairRow;
  onClose: () => void;
}

/**
 * SqlViewer — Plan 125 F6. Modal de solo lectura del contenido de un script
 * generado. Si la fila tiene backupFile o rollbackFile, muestra AMBOS lados
 * (split vertical): izquierda backup/rollback, derecha paridad — el pareo
 * 1:1 literal en pantalla. Stacky genera; VOS ejecutás (nunca hay botón de
 * "ejecutar" acá).
 */
export function SqlViewer({ runId, row, onClose }: Props) {
  const [mainText, setMainText] = useState<string>("Cargando...");
  const [pairText, setPairText] = useState<string>("Cargando...");

  const pairFile = row.backupFile || row.rollbackFile;
  const pairLabel = row.backupFile ? "Backup" : "Rollback";

  useEffect(() => {
    let cancelled = false;
    DbCompare.getScriptFileText(runId, row.file)
      .then((text) => {
        if (!cancelled) setMainText(text);
      })
      .catch((err) => {
        if (!cancelled) setMainText(`No se pudo cargar: ${err instanceof Error ? err.message : String(err)}`);
      });
    if (pairFile) {
      DbCompare.getScriptFileText(runId, pairFile)
        .then((text) => {
          if (!cancelled) setPairText(text);
        })
        .catch((err) => {
          if (!cancelled) setPairText(`No se pudo cargar: ${err instanceof Error ? err.message : String(err)}`);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [runId, row.file, pairFile]);

  const copy = (text: string) => {
    navigator.clipboard?.writeText(text).catch(() => {});
  };

  const download = (path: string) => {
    const a = document.createElement("a");
    a.href = DbCompare.scriptFileUrl(runId, path);
    a.download = path.split("/").pop() || path;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <strong>{row.file}</strong>
          <button onClick={onClose} aria-label="Cerrar">
            ✕
          </button>
        </div>
        <div className={pairFile ? styles.modalSplit : styles.modalSingle}>
          {pairFile && (
            <div className={styles.modalPane}>
              <div className={styles.modalPaneHeader}>
                <span>
                  {pairLabel}: {pairFile}
                </span>
                <div className={styles.modalPaneActions}>
                  <button onClick={() => copy(pairText)}>Copiar</button>
                  <button onClick={() => download(pairFile)}>Descargar</button>
                </div>
              </div>
              <pre className={styles.sqlPre}>{pairText}</pre>
            </div>
          )}
          <div className={styles.modalPane}>
            <div className={styles.modalPaneHeader}>
              <span>Paridad: {row.file}</span>
              <div className={styles.modalPaneActions}>
                <button onClick={() => copy(mainText)}>Copiar</button>
                <button onClick={() => download(row.file)}>Descargar</button>
              </div>
            </div>
            <pre className={styles.sqlPre}>{mainText}</pre>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SqlViewer;
