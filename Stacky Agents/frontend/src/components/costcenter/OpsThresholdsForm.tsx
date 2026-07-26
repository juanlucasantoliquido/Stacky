import { useState } from "react";

import { Ops } from "../../api/endpoints";
import type { OpsThresholds } from "../../lib/opsTelemetryTypes";
import { Button, Field, Input, SectionHeader, firstErrorFieldId } from "../ui";
import Toast, { type ToastState } from "../Toast";
import styles from "./OpsThresholdsForm.module.css";

/**
 * Plan 171 F6 — Umbrales de los avisos, editables por el operador.
 *
 * Human-in-the-loop explícito: sin auto-guardado. Los umbrales tienen defaults
 * sensatos, así que editarlos es OPCIONAL — el presupuesto diario nace vacío
 * (regla apagada, cero ruido).
 */

const PREFIX = "ops-threshold";
const DOM_ORDER = ["error_rate_warn", "stall_minutes", "daily_budget_usd"] as const;

type Errors = Record<string, string>;

function validate(errorRate: string, stall: string, budget: string): Errors {
  const errors: Errors = {};

  const rate = Number(errorRate);
  if (errorRate.trim() === "" || Number.isNaN(rate) || rate < 0 || rate > 1) {
    errors.error_rate_warn = "Tiene que ser un número entre 0 y 1.";
  }

  const minutes = Number(stall);
  if (stall.trim() === "" || !Number.isInteger(minutes) || minutes < 1) {
    errors.stall_minutes = "Tiene que ser un número entero de 1 minuto o más.";
  }

  if (budget.trim() !== "") {
    const usd = Number(budget);
    if (Number.isNaN(usd) || usd <= 0) {
      errors.daily_budget_usd = "Dejalo vacío para no avisar, o poné un monto mayor que 0.";
    }
  }
  return errors;
}

export default function OpsThresholdsForm({
  initial,
  onSaved,
}: {
  initial: OpsThresholds;
  onSaved: (t: OpsThresholds) => void;
}) {
  const [errorRate, setErrorRate] = useState(String(initial.error_rate_warn));
  const [stall, setStall] = useState(String(initial.stall_minutes));
  const [budget, setBudget] = useState(
    initial.daily_budget_usd == null ? "" : String(initial.daily_budget_usd),
  );
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  const handleSubmit = async () => {
    const found = validate(errorRate, stall, budget);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      const id = firstErrorFieldId(PREFIX, DOM_ORDER, found);
      if (id) document.getElementById(id)?.focus();
      return;
    }
    setSaving(true);
    try {
      const res = await Ops.saveThresholds({
        error_rate_warn: Number(errorRate),
        stall_minutes: Number(stall),
        daily_budget_usd: budget.trim() === "" ? null : Number(budget),
      });
      setToast({ variant: "success", body: "Umbrales guardados" });
      onSaved(res.thresholds);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "No se pudieron guardar los umbrales";
      setToast({ variant: "error", body: msg });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className={styles.section}>
      <SectionHeader
        title="Umbrales de los avisos"
        subtitle="Los avisos son informativos: Stacky nunca corta ni reintenta por su cuenta."
      />
      <div className={styles.grid}>
        <Field
          label="Umbral de tasa de error (0-1)"
          id={`${PREFIX}-error_rate_warn`}
          error={errors.error_rate_warn}
        >
          {(ctl) => (
            <Input {...ctl} value={errorRate} onChange={(e) => setErrorRate(e.target.value)} />
          )}
        </Field>
        <Field
          label="Minutos para considerar colgada"
          id={`${PREFIX}-stall_minutes`}
          error={errors.stall_minutes}
        >
          {(ctl) => <Input {...ctl} value={stall} onChange={(e) => setStall(e.target.value)} />}
        </Field>
        <Field
          label="Presupuesto diario USD (vacío = sin aviso)"
          id={`${PREFIX}-daily_budget_usd`}
          error={errors.daily_budget_usd}
        >
          {(ctl) => <Input {...ctl} value={budget} onChange={(e) => setBudget(e.target.value)} />}
        </Field>
      </div>
      <div className={styles.actions}>
        <Button onClick={handleSubmit} disabled={saving}>
          {saving ? "Guardando…" : "Guardar umbrales"}
        </Button>
        <p className={styles.hint}>Nada se guarda hasta que apretás Guardar.</p>
      </div>
      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </section>
  );
}
