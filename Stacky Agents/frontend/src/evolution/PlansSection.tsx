// Plan 237 F5 — sección "Planes" del Centro de Evolución (SOLO LECTURA).
// Responde "¿qué plan implemento ahora?": el primer grupo no vacío es siempre
// "Sin implementar". CERO pollers (G5): carga on-mount + botón Refrescar.
// CERO estilos en línea y cero colores literales (G6): todo por el .module.css.
// CERO escritura: no ejecuta planes, solo ofrece texto copiable (G2).
import { useCallback, useEffect, useMemo, useState } from "react";
import { Evolution } from "../api/endpoints";
import { Button, Card, SectionHeader, Input } from "../components/ui";
import SkeletonList from "../components/SkeletonList";
import EmptyState from "../components/EmptyState";
import Toast, { type ToastState } from "../components/Toast";
import { copyText, COPY_TOAST_SUCCESS, COPY_TOAST_ERROR } from "../services/copyService";
import {
  BUCKET_META, BUCKETS_ABIERTOS_POR_DEFECTO,
  groupByBucket, filterByText, censusSummary, numberingAlert,
  type PlansTriageDto, type PlanTriageCard, type TriageBucket,
} from "./plansTriageModel";
import styles from "./PlansSection.module.css";
import { userFacingMessage } from "../api/gatewayError"; // Plan 273 F4.6

export default function PlansSection() {
  const [status, setStatus] = useState<"loading" | "hidden" | "error" | "ready">("loading");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [data, setData] = useState<PlansTriageDto | null>(null);
  const [texto, setTexto] = useState("");
  const [toast, setToast] = useState<ToastState | null>(null);

  const load = useCallback(async (refresh = false) => {
    try {
      const h = (await Evolution.plansHealth()) as { flag_enabled: boolean };
      if (!h.flag_enabled) {
        setStatus("hidden");
        return;
      }
      setStatus("loading");
      const r = await Evolution.plans(refresh);
      if (!r.ok) {
        setErrorMsg(`No se pudo leer el inventario de planes (${r.status}).`);
        setStatus("error");
        return;
      }
      setData(r.data as PlansTriageDto);
      setStatus("ready");
    } catch (e) {
      setErrorMsg(userFacingMessage(e).title);
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const grupos = useMemo(
    () => groupByBucket(filterByText(data?.plans ?? [], texto)),
    [data, texto],
  );

  const copiar = async (valor: string) => {
    const r = await copyText(valor);
    setToast({ variant: r.ok ? "success" : "error", body: r.ok ? COPY_TOAST_SUCCESS : COPY_TOAST_ERROR });
  };

  if (status === "hidden") return null;
  if (status === "loading") return <SkeletonList />;
  if (status === "error") {
    return (
      <EmptyState
        variant="generic"
        title="No se pudieron leer los planes"
        message={errorMsg ?? undefined}
      />
    );
  }

  const dto = data as PlansTriageDto;
  const aviso = numberingAlert(dto.numbering);
  const censo = censusSummary(dto.census);
  const hayReserva =
    dto.next_free_number_raw !== undefined && dto.next_free_number_raw !== dto.next_free_number;

  return (
    <div className={styles.section}>
      <SectionHeader
        title="Planes"
        actions={
          <Button variant="ghost" size="sm" onClick={() => void load(true)}>
            Refrescar
          </Button>
        }
      />
      <Card>
        <div className={styles.resumenRow}>
          <span className={styles.proximo}>Próximo Nº libre: {dto.next_free_number}</span>
          {hayReserva && (
            <span className={styles.reservados}>
              …{dto.reserved_count ?? 0} números reservados por el roadmap
            </span>
          )}
          <div className={styles.chips}>
            {(dto.triage_order as TriageBucket[]).map((b) => (
              <span key={b} className={`${styles.chip} ${styles[BUCKET_META[b].tone]}`}>
                {BUCKET_META[b].label} {dto.triage_totals[b] ?? 0}
              </span>
            ))}
          </div>
        </div>
        {aviso !== null && (
          <p className={styles.alerta} role="status">
            {aviso}
          </p>
        )}
        {censo !== null && <p className={styles.census}>{censo}</p>}
      </Card>

      <div className={styles.filtro}>
        <Input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Filtrar por número, título o slug"
          aria-label="Filtrar planes"
        />
      </div>

      {grupos.map(({ bucket, cards }) =>
        cards.length === 0 ? null : (
          <details
            key={bucket}
            open={BUCKETS_ABIERTOS_POR_DEFECTO.includes(bucket)}
            className={styles.grupo}
          >
            <summary className={`${styles.resumen} ${styles[BUCKET_META[bucket].tone]}`}>
              {BUCKET_META[bucket].label} ({cards.length})
            </summary>
            <p className={styles.hint}>{BUCKET_META[bucket].hint}</p>
            <table className={styles.tabla}>
              <thead>
                <tr>
                  <th>Nº</th>
                  <th>Título</th>
                  <th>Estado</th>
                  <th>Supervisión</th>
                  <th>Push</th>
                  <th>Acción sugerida</th>
                </tr>
              </thead>
              <tbody>
                {cards.map((card: PlanTriageCard) => (
                  <tr key={`${card.number}-${card.filename ?? card.slug}`}>
                    <td>
                      {card.number_str}
                      {card.duplicate && <span className={styles.badgeDup}>DUP</span>}
                    </td>
                    <td>
                      {card.title}
                      {(card.version || card.fecha) && (
                        <span className={styles.subtitulo}>
                          {[card.version ? `v${card.version}` : null, card.fecha]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      )}
                    </td>
                    <td>{card.estado_efectivo}</td>
                    <td>
                      {card.ledger === null
                        ? "—"
                        : card.ledger.doc_drift === true
                          ? "drift"
                          : `OK ${card.ledger.veredicto}`}
                    </td>
                    <td>{card.unpushed === null ? "—" : card.unpushed ? "pendiente" : "ok"}</td>
                    <td>
                      <div className={styles.acciones}>
                        <span>{card.suggested_action.label}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            void copiar(
                              card.suggested_action.command ??
                                card.suggested_action.natural_language,
                            )
                          }
                        >
                          Copiar comando
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => void copiar(card.suggested_action.natural_language)}
                        >
                          Copiar en texto
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        ),
      )}
      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
