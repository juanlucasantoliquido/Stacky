import { useEffect, useState } from "react";

import { Incidents } from "../api/endpoints";
import SqlExecPanel from "./dbcompare/SqlExecPanel";
import type { ScriptRef } from "./dbcompare/sqlExecPanelLogic";
import { badge, scriptsSummary, type DeployNeed } from "./sqlDeployBadge";
import styles from "./IncidentResolverModal.module.css";

/**
 * Plan 200 F4 — "Acá hay SQL para desplegar", visible sin leer el detalle.
 *
 * El detector es determinista: un `.sql` adjunto da certeza alta; solo palabras
 * clave da sospecha. Los dos tonos son distintos a propósito — si la sospecha se
 * viera igual que la certeza, el operador dejaría de mirar los avisos fuertes.
 *
 * Debajo va el panel de ejecución (R3/R4), que muestra la traza aunque la
 * ejecución esté deshabilitada.
 */
export function IncidentSqlDeploySection({ incidentId }: { incidentId: string }) {
  const [need, setNeed] = useState<DeployNeed | null>(null);

  useEffect(() => {
    let vivo = true;
    Incidents.sqlDeploy(incidentId)
      .then((r) => vivo && setNeed(r as unknown as DeployNeed))
      // 404 = flag apagada: la incidencia se ve exactamente como antes.
      .catch(() => vivo && setNeed(null));
    return () => {
      vivo = false;
    };
  }, [incidentId]);

  if (!need) return null;
  const aviso = badge(need);
  if (!aviso.show) return null;

  const scripts: ScriptRef[] = (need.scripts ?? []).map((s) => ({
    source: (s.source as ScriptRef["source"]) ?? "incident_attachment",
    sha256: s.sha256,
    name: s.name,
    incident_id: incidentId,
  }));

  return (
    <div className={styles.previewSection}>
      <div className={aviso.tone === "warn" ? styles.previewWarnings : styles.previewHeader}>
        {aviso.text}
      </div>
      {scriptsSummary(need) && <p className={styles.hint}>{scriptsSummary(need)}</p>}
      {need.reason && <p className={styles.hint}>{need.reason}</p>}
      <SqlExecPanel scripts={scripts} incidentId={incidentId} ticketRef={null} />
    </div>
  );
}

export default IncidentSqlDeploySection;
