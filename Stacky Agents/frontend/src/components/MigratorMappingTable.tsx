/**
 * Plan 74 F7 — Tabla del mapa de migración ADO → GitLab.
 *
 * Lee GET /api/migrator/{project}/mapping y muestra las filas.
 * Permite descargar el CSV vía Accept: text/csv (usa un <a href> con URL directa).
 */
import { useQuery } from "@tanstack/react-query";
import { Migrator } from "../api/endpoints";

interface Props {
  stackyProject: string;
}

export default function MigratorMappingTable({ stackyProject }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["migrator-mapping", stackyProject],
    queryFn: () => Migrator.mapping(stackyProject),
    enabled: !!stackyProject,
  });

  if (isLoading) return <p style={{ fontSize: 13, color: "#888" }}>Cargando mapa...</p>;
  if (error) return <p style={{ fontSize: 13, color: "#c00" }}>Error al cargar el mapa.</p>;

  const rows = data?.rows ?? [];

  if (rows.length === 0) {
    return <p style={{ fontSize: 13, color: "#888" }}>No hay items migrados todavia.</p>;
  }

  const csvUrl = `/api/migrator/${encodeURIComponent(stackyProject)}/mapping`;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 13, color: "#555" }}>{rows.length} item(s) migrado(s)</span>
        <a
          href={csvUrl}
          download={`mapping_${stackyProject}.csv`}
          style={{ fontSize: 12, textDecoration: "none", color: "#0969da" }}
        >
          Descargar CSV
        </a>
      </div>
      <table
        style={{
          borderCollapse: "collapse",
          width: "100%",
          fontSize: 12,
          fontFamily: "monospace",
        }}
      >
        <thead>
          <tr style={{ background: "#f6f8fa" }}>
            <th style={{ border: "1px solid #d0d7de", padding: "4px 8px", textAlign: "left" }}>ADO ID</th>
            <th style={{ border: "1px solid #d0d7de", padding: "4px 8px", textAlign: "left" }}>Tipo</th>
            <th style={{ border: "1px solid #d0d7de", padding: "4px 8px", textAlign: "left" }}>GitLab IID</th>
            <th style={{ border: "1px solid #d0d7de", padding: "4px 8px", textAlign: "left" }}>URL GitLab</th>
            <th style={{ border: "1px solid #d0d7de", padding: "4px 8px", textAlign: "left" }}>Corrida</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.ado_id}>
              <td style={{ border: "1px solid #d0d7de", padding: "3px 8px" }}>{row.ado_id}</td>
              <td style={{ border: "1px solid #d0d7de", padding: "3px 8px" }}>{row.ado_type}</td>
              <td style={{ border: "1px solid #d0d7de", padding: "3px 8px" }}>{row.gitlab_iid}</td>
              <td style={{ border: "1px solid #d0d7de", padding: "3px 8px" }}>
                {row.gitlab_web_url ? (
                  <a href={row.gitlab_web_url} target="_blank" rel="noreferrer" style={{ color: "#0969da" }}>
                    {row.gitlab_iid || row.gitlab_web_url}
                  </a>
                ) : (
                  "—"
                )}
              </td>
              <td style={{ border: "1px solid #d0d7de", padding: "3px 8px", color: "#888" }}>
                {row.migration_run}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
