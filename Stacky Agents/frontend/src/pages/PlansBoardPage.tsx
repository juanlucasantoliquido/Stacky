/**
 * Plan 128 — Tablero de evolución de planes (solo lectura).
 *
 * Visible solo cuando STACKY_PLANS_BOARD_ENABLED=true (gate en App.tsx).
 * La página JAMÁS ejecuta nada: muestra estado del pipeline
 * proponer→criticar→implementar→supervisar por plan, y ofrece una acción
 * sugerida COPIABLE al portapapeles (el operador la pega y ejecuta él mismo).
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PlansBoard, type PlansBoardDetailDto } from "../api/endpoints";
import {
  ESTADO_CHIP,
  buildCopyPayload,
  estadoChip,
  filterPlans,
  type BoardFilters,
  type EstadoPlan,
  type PlanCardDto,
  type SuggestedAction,
} from "../plansBoard/model";
import styles from "./PlansBoardPage.module.css";

const ESTADOS: (EstadoPlan | "TODOS")[] = [
  "TODOS",
  "PROPUESTO",
  "CRITICADO",
  "IMPLEMENTADO",
  "IMPLEMENTADO_PARCIAL",
  "APROBADO",
  "SIN_ESTADO",
];

function CopyButton({
  action,
  variant,
  copiedKey,
  onCopy,
}: {
  action: SuggestedAction;
  variant: "primary" | "natural";
  copiedKey: string | null;
  onCopy: (text: string, key: string) => void;
}) {
  const text = variant === "primary" ? buildCopyPayload(action) : action.natural_language;
  const key = `${variant}:${text}`;
  const label = variant === "primary" ? "📋" : "💬";
  const isCopied = copiedKey === key;
  return (
    <button
      type="button"
      className={styles.copyBtn}
      title={variant === "primary" ? "Copiar comando/acción" : "Copiar en lenguaje natural"}
      onClick={(ev) => {
        ev.stopPropagation();
        onCopy(text, key);
      }}
    >
      {isCopied ? "Copiado ✓" : label}
    </button>
  );
}

export default function PlansBoardPage() {
  const [texto, setTexto] = useState("");
  const [estado, setEstado] = useState<EstadoPlan | "TODOS">("TODOS");
  const [soloPendientesPush, setSoloPendientesPush] = useState(false);
  const [soloSinSupervisar, setSoloSinSupervisar] = useState(false);
  const [selectedNumber, setSelectedNumber] = useState<number | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [copyFailed, setCopyFailed] = useState(false);

  const boardQuery = useQuery({
    queryKey: ["plans-board-list"],
    queryFn: () => PlansBoard.list(),
    retry: false,
  });

  const detailQuery = useQuery({
    queryKey: ["plans-board-detail", selectedNumber],
    queryFn: () => PlansBoard.detail(selectedNumber as number),
    enabled: selectedNumber !== null,
    retry: false,
  });

  const handleCopy = (text: string, key: string) => {
    try {
      navigator.clipboard
        .writeText(text)
        .then(() => {
          setCopyFailed(false);
          setCopiedKey(key);
          window.setTimeout(() => setCopiedKey((k) => (k === key ? null : k)), 1500);
        })
        .catch(() => setCopyFailed(true));
    } catch {
      setCopyFailed(true);
    }
  };

  useEffect(() => {
    if (!copyFailed) return;
    const t = window.setTimeout(() => setCopyFailed(false), 2000);
    return () => window.clearTimeout(t);
  }, [copyFailed]);

  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setSelectedNumber(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const board = boardQuery.data;
  const filters: BoardFilters = { texto, estado, soloPendientesPush, soloSinSupervisar };
  const filtered = useMemo(() => (board ? filterPlans(board.plans, filters) : []), [board, texto, estado, soloPendientesPush, soloSinSupervisar]);

  if (boardQuery.isLoading) {
    return (
      <div className={styles.root}>
        <p className={styles.loading}>Cargando planes…</p>
      </div>
    );
  }

  if (boardQuery.isError || !board) {
    return (
      <div className={styles.root}>
        <div className={styles.errorBanner}>
          <span>No se pudo cargar el tablero de planes.</span>
          <button type="button" className={styles.retryBtn} onClick={() => boardQuery.refetch()}>
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  const gitAvailable = board.git_available;

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>🧭 Planes</h2>
        <span className={styles.subtitle}>
          Tablero de solo lectura del pipeline proponer → criticar → implementar → supervisar.
        </span>
      </div>

      {/* Hero */}
      <div className={styles.hero}>
        <div className={styles.heroCard}>
          <span className={styles.heroLabel}>Próximo Nº libre</span>
          <span className={styles.heroValue}>{board.next_free_number}</span>
        </div>
        {(Object.keys(ESTADO_CHIP) as EstadoPlan[]).map((key) => (
          <div key={key} className={styles.chipCard} style={{ borderColor: ESTADO_CHIP[key].color }}>
            <span className={styles.chipDot} style={{ background: ESTADO_CHIP[key].color }} />
            <span>{ESTADO_CHIP[key].label}</span>
            <strong>{board.totals[key] ?? 0}</strong>
          </div>
        ))}
        {gitAvailable && (
          <div className={styles.heroCard}>
            <span className={styles.heroLabel}>⬆️ Sin push</span>
            <span className={styles.heroValue}>{board.totals.unpushed ?? 0}</span>
          </div>
        )}
        {(board.totals.duplicados ?? 0) > 0 && (
          <div className={`${styles.heroCard} ${styles.heroWarn}`}>
            <span className={styles.heroLabel}>⚠️ Duplicados</span>
            <span className={styles.heroValue}>{board.totals.duplicados}</span>
          </div>
        )}
        <button type="button" className={styles.refreshBtn} onClick={() => boardQuery.refetch()}>
          ↻ Refrescar
        </button>
      </div>

      {/* Filtros */}
      <div className={styles.filters}>
        <input
          className={styles.filterInput}
          placeholder="Buscar por número, título o slug…"
          value={texto}
          onChange={(ev) => setTexto(ev.target.value)}
        />
        <select className={styles.filterSelect} value={estado} onChange={(ev) => setEstado(ev.target.value as EstadoPlan | "TODOS")}>
          {ESTADOS.map((e) => (
            <option key={e} value={e}>
              {e === "TODOS" ? "Todos los estados" : ESTADO_CHIP[e].label}
            </option>
          ))}
        </select>
        <label className={styles.filterCheck} title={gitAvailable ? undefined : "sin datos de git"}>
          <input
            type="checkbox"
            checked={soloPendientesPush}
            disabled={!gitAvailable}
            onChange={(ev) => setSoloPendientesPush(ev.target.checked)}
          />
          Solo pendientes de push
        </label>
        <label className={styles.filterCheck}>
          <input type="checkbox" checked={soloSinSupervisar} onChange={(ev) => setSoloSinSupervisar(ev.target.checked)} />
          Solo sin supervisar
        </label>
      </div>

      {/* Tabla / empty state */}
      {!board.docs_dir_found || board.plans.length === 0 ? (
        <p className={styles.empty}>No se encontraron docs de planes en este deploy</p>
      ) : (
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Nº</th>
                <th>Título</th>
                <th>Estado</th>
                <th>Juez</th>
                <th>Supervisión</th>
                <th>Push</th>
                <th>Acción sugerida</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((card: PlanCardDto) => {
                const chip = estadoChip(card);
                return (
                  <tr key={`${card.number}-${card.filename}`} className={styles.row} onClick={() => setSelectedNumber(card.number)}>
                    <td>
                      {card.number_str}
                      {card.duplicate && <span className={styles.dupBadge}>DUP</span>}
                    </td>
                    <td className={styles.titleCell}>
                      <div>{card.title}</div>
                      <div className={styles.subCell}>
                        {[card.version ? `v${card.version}` : null, card.fecha].filter(Boolean).join(" · ")}
                      </div>
                    </td>
                    <td>
                      <span className={styles.stateChip} style={{ background: chip.color }}>
                        {chip.label}
                      </span>
                    </td>
                    <td>{card.veredicto ?? "—"}</td>
                    <td>
                      {card.ledger === null
                        ? "—"
                        : card.ledger.doc_drift === true
                          ? "⚠️ drift"
                          : `✅ ${card.ledger.veredicto}`}
                    </td>
                    <td>{card.unpushed === null ? "—" : card.unpushed ? "⬆️ pendiente" : "✓"}</td>
                    <td className={styles.actionCell}>
                      <span>{card.suggested_action.label}</span>
                      <CopyButton action={card.suggested_action} variant="primary" copiedKey={copiedKey} onCopy={handleCopy} />
                      <CopyButton action={card.suggested_action} variant="natural" copiedKey={copiedKey} onCopy={handleCopy} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {copyFailed && <div className={styles.copyFailBanner}>No se pudo copiar</div>}

      {/* Drawer de detalle */}
      {selectedNumber !== null && (
        <div className={styles.drawerOverlay} onClick={() => setSelectedNumber(null)}>
          <div className={styles.drawer} onClick={(ev) => ev.stopPropagation()}>
            <button type="button" className={styles.drawerClose} onClick={() => setSelectedNumber(null)}>
              ✕
            </button>
            {detailQuery.isLoading && <p>Cargando detalle…</p>}
            {detailQuery.data && (
              <DrawerContent data={detailQuery.data} copiedKey={copiedKey} onCopy={handleCopy} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DrawerContent({
  data,
  copiedKey,
  onCopy,
}: {
  data: PlansBoardDetailDto;
  copiedKey: string | null;
  onCopy: (text: string, key: string) => void;
}) {
  const { plan, duplicates, head_excerpt } = data;
  return (
    <div>
      <h3>
        Plan {plan.number_str} — {plan.title}
      </h3>
      <p className={styles.subCell}>
        Estado: {plan.estado} · Efectivo: {plan.estado_efectivo}
        {plan.version ? ` · v${plan.version}` : ""}
        {plan.fecha ? ` · ${plan.fecha}` : ""}
      </p>
      <p>{plan.suggested_action.label}</p>
      <div className={styles.drawerCopyRow}>
        <CopyButton action={plan.suggested_action} variant="primary" copiedKey={copiedKey} onCopy={onCopy} />
        <CopyButton action={plan.suggested_action} variant="natural" copiedKey={copiedKey} onCopy={onCopy} />
      </div>
      {duplicates.length > 0 && (
        <div className={styles.dupWarning}>
          ⚠️ Número duplicado por: {duplicates.map((d) => d.filename).join(", ")}
        </div>
      )}
      <pre className={styles.headExcerpt}>{head_excerpt}</pre>
    </div>
  );
}
