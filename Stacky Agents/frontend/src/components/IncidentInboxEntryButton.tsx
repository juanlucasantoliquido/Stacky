/**
 * Plan 238 F8 — Punto de entrada a la bandeja de incidencias desde el tablero.
 * AUTOCONTENIDO a proposito: TicketBoard.tsx solo agrega el import y el
 * elemento. Cero props, cero estilos en linea, CSS module propio (no se toca
 * TicketBoard.module.css, que esta disputado por otra sesion).
 */
import { useQuery } from "@tanstack/react-query";
import { IncidentInbox } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { TAB_PATHS } from "../services/routes";
import { INCIDENT_ICON } from "../utils/workItemTypeColor";
import styles from "./IncidentInboxEntryButton.module.css";

export default function IncidentInboxEntryButton() {
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);

  const statusQ = useQuery({
    queryKey: ["incident-inbox-status", activeProjectName],
    queryFn: () => IncidentInbox.status(activeProjectName),
    staleTime: 5 * 60 * 1000,
  });

  const itemsQ = useQuery({
    queryKey: ["incident-inbox-items", activeProjectName, "open"],
    queryFn: () => IncidentInbox.items(activeProjectName, "open"),
    enabled: statusQ.data?.data?.enabled === true,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  if (statusQ.data?.data?.enabled !== true) return null;

  const openCount = itemsQ.data?.data?.counts?.open ?? null;

  const go = () => {
    // NAVEGACION DEL ROUTER CASERO. Verificado 2026-07-25: `navigateToRoute`
    // es una CLAUSURA LOCAL del componente App, NO un export. PROHIBIDO
    // exportarla: crearia el ciclo App -> TicketBoard -> este componente -> App.
    // El listener de App escucha "popstate" y re-deriva TODO el estado con
    // parseRoute, asi que este par es suficiente.
    window.history.pushState({}, "", TAB_PATHS.incidencias);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return (
    <button
      className={styles.entryBtn}
      onClick={go}
      title="Ver solo las incidencias, con las abiertas primero"
    >
      {INCIDENT_ICON} Incidencias
      {openCount !== null && openCount > 0 && (
        <span className={styles.badge} aria-label={`${openCount} incidencias abiertas`}>
          {openCount}
        </span>
      )}
    </button>
  );
}
