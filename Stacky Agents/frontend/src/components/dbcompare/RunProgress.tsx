import { useEffect } from "react";
import { DbCompare } from "../../api/endpoints";
import { useCompareRun } from "./useCompareRun";
import { PHASE_ORDER, phaseState } from "./runProgressLogic";
import type { CompareRun } from "./dbcompareTypes";
import styles from "./dbcompare.module.css";

const PHASE_LABEL: Record<(typeof PHASE_ORDER)[number], string> = {
  queued: "En cola",
  snapshot_source: "Snapshot origen",
  snapshot_target: "Snapshot destino",
  diff: "Comparando",
  done: "Listo",
};

interface Props {
  runId: string;
  sourceAlias: string;
  targetAlias: string;
  mode: "fresh" | "cached";
  onDone: (run: CompareRun) => void;
}

/**
 * Plan 124 F2 — progreso vivo de una corrida: stepper de las 4 fases reales (runProgressLogic.ts,
 * ya testeado) con polling (useCompareRun.ts, ya testeado). `error`/`stale` se muestran como
 * cards dedicadas en vez de intentar seguir el stepper.
 */
export function RunProgress({ runId, sourceAlias, targetAlias, mode, onDone }: Props) {
  const { run, error } = useCompareRun(runId);

  // Transición a done se maneja en efecto (no en render) para no disparar un setState del
  // padre mientras este componente todavía se está renderizando.
  useEffect(() => {
    if (run && run.status === "done") {
      onDone(run);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.run_id, run?.status]);

  const handleRetry = async () => {
    // [FIX C6 de la crítica v2] Reintentar reinvoca compare con el MISMO par/modo ya elegido;
    // el runId nuevo lo recibe el padre vía onDone-como-relaunch no aplica acá: RunProgress
    // queda en su propia vista mostrando la corrida NUEVA (el padre decide cómo remontar).
    const res = await DbCompare.compare({ source_alias: sourceAlias, target_alias: targetAlias, mode });
    onDone(res.run);
  };

  if (error) {
    return (
      <div className={styles.errorBanner}>
        Error al consultar la corrida: {error}
      </div>
    );
  }

  if (!run) {
    return <div className={styles.recency}>Cargando estado de la corrida…</div>;
  }

  if (run.status === "error") {
    return (
      <div className={styles.errorBanner}>
        <div>{run.error || "La corrida terminó con error."}</div>
        <button onClick={handleRetry}>Reintentar</button>
      </div>
    );
  }

  if (run.stale) {
    return (
      <div className={styles.staleCard}>
        Corrida abandonada (backend reiniciado); relanzá.
        <div>
          <button onClick={handleRetry}>Reintentar</button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.stepper}>
      {PHASE_ORDER.filter((p) => p !== "done").map((phase) => {
        const state = phaseState(run, phase);
        const cls =
          state === "active" ? styles.stepActive : state === "done" ? styles.stepDone : styles.stepPending;
        return (
          <div key={phase} className={`${styles.step} ${cls}`}>
            {PHASE_LABEL[phase]}
          </div>
        );
      })}
    </div>
  );
}

export default RunProgress;
