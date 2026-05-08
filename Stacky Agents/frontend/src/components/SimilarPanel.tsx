/*
 * FA-45 + FA-14 — Panel desplegable con ejecuciones similares + graveyard.
 * - "Similares aprobadas" (FA-45): top-K execs aprobadas parecidas al ticket actual.
 * - "Graveyard" (FA-14): execs descartadas / fallidas que matchean el query del operador.
 * Se abre desde el editor con un botón. No bloquea la UI.
 */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Similarity, type SimilarHit } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./SimilarPanel.module.css";

type Tab = "approved" | "graveyard";

export default function SimilarPanel() {
  const { activeTicketId, activeAgentType, setActiveExecution } = useWorkbench();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("approved");
  const [graveyardQuery, setGraveyardQuery] = useState("");

  const approvedQ = useQuery({
    queryKey: ["similar-approved", activeTicketId, activeAgentType],
    queryFn: () => Similarity.forTicket(activeTicketId!, activeAgentType ?? undefined, 5),
    enabled: open && tab === "approved" && activeTicketId != null,
  });

  const graveyardQ = useQuery({
    queryKey: ["graveyard", graveyardQuery, activeAgentType],
    queryFn: () => Similarity.graveyard(graveyardQuery, activeAgentType ?? undefined, 10),
    enabled: open && tab === "graveyard" && graveyardQuery.length >= 3,
  });

  if (!activeTicketId) return null;

  return (
    <div className={styles.wrapper}>
      <button
        className={styles.toggle}
        onClick={() => setOpen((v) => !v)}
        title="Buscar ejecuciones similares aprobadas (FA-45) o descartadas (FA-14)"
      >
        🔍 {open ? "Ocultar" : "Buscar similares & graveyard"}
      </button>

      {open && (
        <div className={styles.panel}>
          <div className={styles.tabs}>
            <button
              className={`${styles.tab} ${tab === "approved" ? styles.active : ""}`}
              onClick={() => setTab("approved")}
            >
              ✓ Similares aprobadas
            </button>
            <button
              className={`${styles.tab} ${tab === "graveyard" ? styles.active : ""}`}
              onClick={() => setTab("graveyard")}
            >
              ⚰ Graveyard
            </button>
          </div>

          {tab === "approved" && (
            <ResultList
              loading={approvedQ.isLoading}
              hits={approvedQ.data ?? []}
              onClick={setActiveExecution}
              empty="No hay ejecuciones similares aprobadas todavía."
            />
          )}

          {tab === "graveyard" && (
            <>
              <input
                className={styles.search}
                placeholder="Texto a buscar (mín. 3 caracteres)..."
                value={graveyardQuery}
                onChange={(e) => setGraveyardQuery(e.target.value)}
              />
              {graveyardQuery.length >= 3 && (
                <ResultList
                  loading={graveyardQ.isLoading}
                  hits={graveyardQ.data ?? []}
                  onClick={setActiveExecution}
                  empty="Nada en el graveyard que coincida. Probá otro término."
                />
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ResultList({
  loading,
  hits,
  onClick,
  empty,
}: {
  loading: boolean;
  hits: SimilarHit[];
  onClick: (id: number) => void;
  empty: string;
}) {
  if (loading) return <div className="muted" style={{ padding: 8 }}>buscando…</div>;
  if (hits.length === 0) return <div className="muted" style={{ padding: 8 }}>{empty}</div>;
  return (
    <ul className={styles.list}>
      {hits.map((h) => (
        <li key={h.execution_id}>
          <button className={styles.item} onClick={() => onClick(h.execution_id)}>
            <div className={styles.itemHead}>
              <span className={styles.score}>{Math.round(h.score * 100)}%</span>
              <span className={styles.execId}>#{h.execution_id}</span>
              <span className={styles.agent}>{h.agent_type}</span>
              <span className={styles.ticket}>ADO-{h.ticket_ado_id}</span>
              <span className={styles.verdict} data-v={h.verdict ?? ""}>
                {h.verdict ?? ""}
              </span>
            </div>
            <div className={styles.snippet}>{h.snippet || "(sin snippet)"}</div>
          </button>
        </li>
      ))}
    </ul>
  );
}
