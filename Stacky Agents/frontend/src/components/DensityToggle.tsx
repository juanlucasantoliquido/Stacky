/* Plan 150 F3 — toggle de densidad de interfaz (espejo del radiogroup de tema, 141 F4). */
import { useState } from "react";
import { currentDensity, setDensity } from "../services/densityController";
import type { Density } from "../services/density";
import styles from "./DensityToggle.module.css";

export const DENSITY_OPTIONS: Array<{ value: Density; label: string; hint: string }> = [
  { value: "comodo",   label: "Cómodo",   hint: "Espaciado estándar (por defecto)." },
  { value: "compacto", label: "Compacto", hint: "Más información por pantalla." },
];

export default function DensityToggle() {
  const [choice, setChoice] = useState<Density>(() => currentDensity());

  const pick = (value: Density) => {
    setChoice(value);
    setDensity(value); // aplica al instante, sin re-montar la app
  };

  return (
    <div className={styles.group} role="radiogroup" aria-label="Densidad de la interfaz">
      {DENSITY_OPTIONS.map((opt) => (
        <label
          key={opt.value}
          className={`${styles.option} ${choice === opt.value ? styles.active : ""}`}
        >
          <input
            type="radio"
            name="stacky-density"
            value={opt.value}
            checked={choice === opt.value}
            onChange={() => pick(opt.value)}
            className={styles.radio}
          />
          <span className={styles.optLabel}>{opt.label}</span>
          <span className={styles.optHint}>{opt.hint}</span>
        </label>
      ))}
    </div>
  );
}
