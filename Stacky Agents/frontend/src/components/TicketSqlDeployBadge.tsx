import { useEffect, useState } from "react";

import { Tickets } from "../api/endpoints";
import { badge, type DeployNeed } from "./sqlDeployBadge";

/**
 * Plan 200 F4 — Avisa en la tarjeta que este ticket trae SQL para desplegar.
 *
 * Certeza y sospecha se ven distinto a propósito: un `.sql` adjunto es warn, y
 * "encontré palabras clave" es info. Si la sospecha se viera igual que la
 * certeza, el operador dejaría de mirar los avisos fuertes.
 *
 * 404 (flag apagada o nada que desplegar) ⇒ no se renderiza nada.
 */
export function TicketSqlDeployBadge({
  ticketId,
  className,
}: {
  ticketId: number;
  className?: string;
}) {
  const [need, setNeed] = useState<DeployNeed | null>(null);

  useEffect(() => {
    let vivo = true;
    Tickets.sqlDeploy(ticketId)
      .then((r) => vivo && setNeed(r as unknown as DeployNeed))
      .catch(() => vivo && setNeed(null));
    return () => {
      vivo = false;
    };
  }, [ticketId]);

  if (!need) return null;
  const aviso = badge(need);
  if (!aviso.show) return null;

  return (
    <span className={className} title={aviso.text}>
      {aviso.tone === "warn" ? "🗄 SQL" : "🗄 SQL?"}
    </span>
  );
}

export default TicketSqlDeployBadge;
