/**
 * Stepper.tsx — Plan 294 F8. Primitiva visual de pasos.
 *
 * CASCARON DE PRESENTACION: toda la logica vive en stepperModel.ts, que SI se
 * testea. Este archivo solo pinta. Se verifica con `tsc --noEmit` y con gates
 * estructurales, porque el repo no tiene RTL ni jsdom.
 */
import styles from "./Stepper.module.css";
import { progressLabel, stepStatus, type StepDef, type StepStatus } from "./stepperModel";

export interface StepperProps {
  steps: StepDef[];
  current: string;
  /** Ids de los pasos ya completados. */
  done?: string[];
  "aria-label"?: string;
}

const CLASE_POR_ESTADO: Record<StepStatus, string> = {
  pendiente: "",
  actual: "actual",
  completo: "completo",
  bloqueado: "bloqueado",
};

export default function Stepper({ steps, current, done, ...rest }: StepperProps) {
  const hechos = done ?? [];
  return (
    <div className={styles.stepper} role="list" aria-label={rest["aria-label"]}>
      {steps.map((paso, i) => {
        const estado = stepStatus(steps, current, hechos, paso.id);
        const extra = CLASE_POR_ESTADO[estado];
        const cls = [styles.paso, extra ? styles[extra] : ""].filter(Boolean).join(" ");
        return (
          <div key={paso.id} className={cls} role="listitem" aria-current={estado === "actual"}>
            {i > 0 && <span className={styles.union} aria-hidden="true" />}
            <span className={styles.bolita}>{estado === "completo" ? "✓" : i + 1}</span>
            <span>{paso.label}</span>
          </div>
        );
      })}
      <span className={styles.progreso}>{progressLabel(steps, current)}</span>
    </div>
  );
}
