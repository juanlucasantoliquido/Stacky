import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { TelemetryHarvest } from "../../api/endpoints";
import type {
  HarvestScanOk,
  HarvestScanResponse,
  HarvestSummary,
} from "../../lib/costCenterTypes";
import { Button, Card, Checkbox, Skeleton } from "../ui";
import { formatUsd } from "../../lib/costCenter.logic";
import styles from "./HarvestSection.module.css";

/** El scan devuelve 200 incluso apagado o roto: hay que discriminar por cuerpo. */
function esScanOk(r: HarvestScanResponse | undefined): r is HarvestScanOk {
  return !!r && r.enabled === true && r.ok === true;
}

function esSummary(
  r: { enabled: boolean } | undefined,
): r is HarvestSummary {
  return !!r && r.enabled === true;
}

/** Plan 199 F6 — Cosecha histórica de telemetría desde disco.
 *
 * El backend ya descubre y agrega solo (auto-scan); esta sección le da al
 * operador la parte que no puede automatizarse: VER qué se encontró y decidir
 * si se escribe. Por eso el scan es dry-run primero y el "Aplicar" recién
 * aparece cuando hay un preview con algo real para aplicar (HITL).
 *
 * Si la flag está apagada la sección no se renderiza (no muestra un cartel de
 * error: simplemente no existe, patrón `probeFlagHealth` del 142/171). */
export default function HarvestSection() {
  const queryClient = useQueryClient();
  const [incluirNoAtribuidas, setIncluirNoAtribuidas] = useState(false);
  const [preview, setPreview] = useState<HarvestScanOk | null>(null);
  const [errorScan, setErrorScan] = useState<string | null>(null);
  const [aplicado, setAplicado] = useState<HarvestScanOk | null>(null);

  const healthQ = useQuery({
    queryKey: ["harvest", "health"],
    queryFn: () => TelemetryHarvest.health(),
  });

  const habilitada = healthQ.data?.flag_enabled === true;

  const summaryQ = useQuery({
    queryKey: ["harvest", "summary", incluirNoAtribuidas],
    queryFn: () => TelemetryHarvest.summary({ attributed: !incluirNoAtribuidas }),
    enabled: habilitada,
  });

  const scanM = useMutation({
    mutationFn: (aplicar: boolean) => TelemetryHarvest.scan(aplicar),
    onSuccess: (resp, aplicar) => {
      if (!esScanOk(resp)) {
        // `{enabled:false}` o `{ok:false,error}` — ambos llegan como 200.
        setErrorScan(
          resp && "error" in resp
            ? resp.error
            : "La cosecha quedó deshabilitada mientras corría el scan.",
        );
        setPreview(null);
        return;
      }
      setErrorScan(null);
      if (aplicar) {
        setAplicado(resp);
        setPreview(null);
        // El backfill tocó filas que alimentan los KPIs live del 142.
        queryClient.invalidateQueries({ queryKey: ["cost-center"] });
        queryClient.invalidateQueries({ queryKey: ["harvest"] });
      } else {
        setPreview(resp);
        setAplicado(null);
      }
    },
    onError: (err: unknown) => {
      setErrorScan(err instanceof Error ? err.message : String(err));
      setPreview(null);
    },
  });

  if (healthQ.isLoading) return <Skeleton height={120} />;
  if (!habilitada) return null;

  const resumen = esSummary(summaryQ.data) ? summaryQ.data : null;
  // Sólo tiene sentido ofrecer "Aplicar" si el preview encontró algo que escribir.
  const hayAlgoQueAplicar =
    !!preview && (preview.backfill.backfilled > 0 || preview.ledger.appended > 0);

  return (
    <Card padding="sm">
      <section className={styles.section}>
        <div className={styles.header}>
          <div>
            <div className={styles.title}>Cosecha histórica</div>
            <div className={styles.subtitle}>
              Corridas de Codex y Claude que quedaron en disco y nunca entraron al
              Centro de Costos. El escaneo no escribe nada hasta que lo confirmes.
            </div>
          </div>
          <div className={styles.actions}>
            <Checkbox
              label="Incluir no atribuidas"
              labelClassName={styles.toggle}
              checked={incluirNoAtribuidas}
              onChange={(e) => setIncluirNoAtribuidas(e.target.checked)}
            />
            <Button
              size="sm"
              variant="secondary"
              disabled={scanM.isPending}
              onClick={() => scanM.mutate(false)}
            >
              {scanM.isPending ? "Escaneando…" : "Escanear históricos"}
            </Button>
            {hayAlgoQueAplicar && (
              <Button
                size="sm"
                variant="primary"
                disabled={scanM.isPending}
                onClick={() => scanM.mutate(true)}
              >
                Aplicar cambios
              </Button>
            )}
          </div>
        </div>

        {errorScan && (
          <div className={`${styles.notice} ${styles.noticeError}`}>
            No se pudo completar el escaneo: {errorScan}
          </div>
        )}

        {preview && (
          <div className={`${styles.notice} ${styles.noticePreview}`}>
            Vista previa (no se escribió nada todavía): se encontraron{" "}
            <strong>{preview.discovered}</strong> corridas en disco.{" "}
            <strong>{preview.backfill.backfilled}</strong> filas existentes se
            completarían con su costo y <strong>{preview.ledger.appended}</strong>{" "}
            corridas huérfanas se anexarían a la bitácora
            {preview.ledger.skipped_dup > 0 && (
              <> ({preview.ledger.skipped_dup} ya estaban)</>
            )}
            .{" "}
            {hayAlgoQueAplicar
              ? "Revisá los números y confirmá con “Aplicar cambios”."
              : "No hay nada nuevo para aplicar."}
          </div>
        )}

        {aplicado && (
          <div className={`${styles.notice} ${styles.noticeApplied}`}>
            Listo: se completaron <strong>{aplicado.backfill.backfilled}</strong>{" "}
            filas y se anexaron <strong>{aplicado.ledger.appended}</strong>{" "}
            corridas a la bitácora. Los KPIs de arriba ya incluyen el resultado.
          </div>
        )}

        {summaryQ.isLoading && <Skeleton height={72} />}

        {resumen && (
          <>
            <div className={styles.stats}>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Corridas</span>
                <span className={styles.statValue}>{resumen.runs_total}</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Facturable</span>
                <span className={styles.statValue}>
                  {formatUsd(resumen.billable_usd)}
                </span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Tokens in</span>
                <span className={styles.statValue}>{resumen.tokens_in_total}</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Tokens out</span>
                <span className={styles.statValue}>{resumen.tokens_out_total}</span>
              </div>
            </div>

            {resumen.breakdown.groups.length > 0 && (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>{resumen.breakdown.dimension}</th>
                      <th className={styles.num}>Corridas</th>
                      <th className={styles.num}>Facturable</th>
                      <th className={styles.num}>Tokens in</th>
                      <th className={styles.num}>Tokens out</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resumen.breakdown.groups.map((g) => (
                      <tr key={g.key}>
                        <td>{g.key || "n/d"}</td>
                        <td className={styles.num}>{g.runs}</td>
                        <td className={styles.num}>{formatUsd(g.billable_usd)}</td>
                        <td className={styles.num}>{g.tokens_in}</td>
                        <td className={styles.num}>{g.tokens_out}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
    </Card>
  );
}
