import { Select } from "./ui";
import {
  buildEffortOptions,
  buildModelOptions,
  pickerCapabilities,
} from "../services/modelEffortOptions";
import type { RuntimeModelCatalog } from "../api/endpoints";
import styles from "./ModelEffortPicker.module.css";

/**
 * Plan 212 F4 — Un solo selector de modelo/effort, en el punto donde se lanza
 * el trabajo.
 *
 * Lo importante: **se ofrecen TODOS los efforts, siempre**. Los que el modelo
 * elegido no soporta se muestran anotados con a qué degradan, no escondidos ni
 * deshabilitados. Esconderlos haría creer que no existen; deshabilitarlos, que
 * están rotos. El operador quiere verlos y decidir.
 */
export function ModelEffortPicker({
  catalog,
  model,
  effort,
  onChange,
  disabled,
  variant = "inline",
}: {
  catalog: RuntimeModelCatalog | undefined;
  model: string | null;
  effort: string | null;
  onChange: (next: { model: string | null; effort: string | null }) => void;
  disabled?: boolean;
  variant?: "inline" | "block";
}) {
  const caps = pickerCapabilities(catalog);
  if (!caps.showModels && !caps.showEfforts) return null;

  const modelos = buildModelOptions(catalog);
  const efforts = buildEffortOptions(catalog, model);
  const elegido = efforts.find((e) => e.id === effort);

  return (
    <div className={`${styles.picker} ${variant === "block" ? styles.block : ""}`}>
      {caps.showModels && (
        <label className={styles.field}>
          Modelo
          <Select
            value={model ?? ""}
            disabled={disabled}
            onChange={(e) => onChange({ model: e.target.value || null, effort })}
          >
            <option value="">Automático</option>
            {modelos.map((m) => (
              <option key={m.id} value={m.id}>
                {m.recommended ? `${m.label} (recomendado)` : m.label}
              </option>
            ))}
          </Select>
        </label>
      )}

      {caps.showEfforts && (
        <label className={styles.field}>
          Effort
          <Select
            value={effort ?? ""}
            disabled={disabled}
            onChange={(e) => onChange({ model, effort: e.target.value || null })}
          >
            <option value="">Automático</option>
            {efforts.map((e) => (
              <option key={e.id} value={e.id}>
                {/* Anotado, no oculto: el operador ve que existe y qué va a pasar. */}
                {e.supported ? e.label : `${e.label} — ${e.note}`}
              </option>
            ))}
          </Select>
        </label>
      )}

      {elegido && !elegido.supported && (
        <span className={styles.note}>
          {elegido.label}: {elegido.note}
        </span>
      )}
      {caps.note && <span className={styles.note}>{caps.note}</span>}
    </div>
  );
}

export default ModelEffortPicker;
