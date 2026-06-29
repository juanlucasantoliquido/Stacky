/**
 * Plan 74 F7 — Pagina del Migrador ADO → GitLab.
 *
 * Solo visible cuando STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=true.
 * Comprueba el health del migrador y renderiza MigratorWizard si la flag está ON,
 * o muestra un mensaje informativo si está OFF.
 */
import { useQuery } from "@tanstack/react-query";
import { Migrator } from "../api/endpoints";
import MigratorWizard from "../components/MigratorWizard";
import MigratorMappingTable from "../components/MigratorMappingTable";
import { useWorkbench } from "../store/workbench";
import styles from "./ExecutionHistoryPage.module.css"; // reutiliza el layout

export default function MigratorPage() {
  const activeProject = useWorkbench((s) => s.activeProject);
  const projectName = activeProject?.name ?? "";

  const healthQuery = useQuery({
    queryKey: ["migrator-health"],
    queryFn: () => Migrator.health(),
    retry: false,
  });

  const flagEnabled = healthQuery.data?.flag_enabled === true;

  if (healthQuery.isLoading) {
    return (
      <div className={styles.page}>
        <p style={{ color: "#888", padding: 24 }}>Verificando disponibilidad del migrador...</p>
      </div>
    );
  }

  if (!flagEnabled) {
    return (
      <div className={styles.page}>
        <h2 style={{ marginBottom: 8 }}>Migrador ADO → GitLab</h2>
        <p style={{ color: "#888", maxWidth: 480 }}>
          El migrador no esta habilitado en esta instalacion. Para activarlo, habilita
          la flag <code>STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED</code> en la seccion{" "}
          <strong>Migrador ADO → GitLab</strong> del panel de flags del arnes
          (Configuracion → Arnes).
        </p>
      </div>
    );
  }

  return (
    <div className={styles.page} style={{ padding: 24 }}>
      <h2 style={{ marginTop: 0, marginBottom: 4 }}>Migrador ADO → GitLab</h2>
      <p style={{ color: "#555", marginBottom: 24, maxWidth: 600 }}>
        Migra work items de Azure DevOps a GitLab de forma segura e idempotente.
        Cada paso requiere confirmacion explicita del operador (HITL).
      </p>

      <MigratorWizard initialProject={projectName} />

      {projectName && (
        <div style={{ marginTop: 32 }}>
          <h3 style={{ marginBottom: 8 }}>Historial de migraciones — {projectName}</h3>
          <MigratorMappingTable stackyProject={projectName} />
        </div>
      )}
    </div>
  );
}
