/**
 * Vista de conjunto del estado de git de TODOS los proyectos (2026-08-02).
 *
 * Nace de un pedido concreto: el operador tenía que cambiar de proyecto activo e
 * ir tildando "Abrir PR" de a uno para descubrir cuáles tienen repositorio
 * reconocido. Acá se ven todos juntos, con el motivo de los que no.
 *
 * La detección la hace el backend EJECUTANDO git contra el `workspace_root` de
 * cada proyecto: no se infiere por el nombre de la carpeta.
 */
import { useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Incidents } from "../api/endpoints";
import { resumirEstadoDeRepos } from "../incidents/incidentDevPrModel";
import styles from "./ReposGitPanel.module.css";

export default function ReposGitPanel() {
  const qc = useQueryClient();
  // Sólo el click del operador fuerza re-mirar el disco. Sin esta marca, el
  // botón invalidaría el cache del navegador y el backend contestaría desde su
  // memo: el operador hace `git init`, aprieta, y sigue viendo "no tiene git".
  const forzar = useRef(false);
  const q = useQuery({
    queryKey: ["dev-pr-preflight-all"],
    queryFn: async () => {
      const refrescar = forzar.current;
      forzar.current = false;
      return Incidents.devPrPreflightAll(refrescar);
    },
    staleTime: 60_000,
  });
  const resumen = resumirEstadoDeRepos(q.data ?? null);

  const revisarDeNuevo = () => {
    forzar.current = true;
    void qc.invalidateQueries({ queryKey: ["dev-pr-preflight-all"] });
    // El tilde de cada tarjeta lee el preflight por proyecto: que se entere.
    void qc.invalidateQueries({ queryKey: ["dev-pr-preflight"] });
  };

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <div>
          <h3 className={styles.title}>Repositorios git de los proyectos</h3>
          <p className={styles.hint}>
            Stacky ejecuta <code>git rev-parse</code> sobre la carpeta de cada proyecto para
            saber si está bajo git. El PR automático del Dev Resolutor sólo puede
            trabajar sobre los que sí lo están.
          </p>
        </div>
        <button className={styles.refresh} onClick={revisarDeNuevo} disabled={q.isFetching}>
          {q.isFetching ? "Revisando…" : "Revisar de nuevo"}
        </button>
      </div>

      {q.data && !q.data.dev_pr_enabled && (
        <div className={styles.avisoFlag}>
          El PR automático está apagado (STACKY_INCIDENT_DEV_PR_ENABLED). El estado de
          los repositorios se muestra igual: son dos cosas distintas.
        </div>
      )}

      {q.isError && (
        <div className={styles.error}>
          No se pudo consultar el estado de los proyectos.
        </div>
      )}
      {resumen.error && <div className={styles.error}>{resumen.error}</div>}

      {q.isLoading ? (
        <p className={styles.hint}>Revisando los repositorios…</p>
      ) : (
        <>
          <p className={styles.conteo}>
            <strong>{resumen.conGit}</strong> con git reconocido ·{" "}
            <strong>{resumen.sinGit}</strong> sin git
          </p>
          {resumen.filas.length === 0 ? (
            <p className={styles.hint}>No hay proyectos configurados.</p>
          ) : (
            <table className={styles.tabla}>
              <thead>
                <tr>
                  <th>Proyecto</th>
                  <th>Git</th>
                  <th>Carpeta / repositorio</th>
                  <th>Detalle</th>
                </tr>
              </thead>
              <tbody>
                {resumen.filas.map((f) => (
                  <tr key={f.project}>
                    <td className={styles.nombre}>{f.project}</td>
                    <td>
                      <span
                        className={
                          f.estado === "con-git" ? styles.badgeOk : styles.badgeMal
                        }
                      >
                        {f.estado === "con-git" ? "Sí" : "No"}
                      </span>
                      {f.proveedor && <span className={styles.proveedor}>{f.proveedor}</span>}
                    </td>
                    <td className={styles.ruta}>
                      <code>{f.repoRoot || f.workspaceRoot || "(sin carpeta configurada)"}</code>
                    </td>
                    <td className={styles.detalle}>{f.detalle}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
