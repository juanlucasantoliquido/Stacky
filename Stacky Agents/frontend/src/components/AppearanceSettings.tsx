import { useState } from "react";
import { readStoredChoice, setTheme } from "../services/themeController";
import type { ThemeChoice } from "../services/theme";
import DensityToggle from "./DensityToggle";
import styles from "./AppearanceSettings.module.css";

export const THEME_OPTIONS: Array<{ value: ThemeChoice; label: string; hint: string }> = [
  { value: "dark", label: "Oscuro", hint: "Tema oscuro (por defecto)." },
  { value: "light", label: "Claro", hint: "Tema claro de alto contraste." },
  { value: "system", label: "Sistema", hint: "Sigue la preferencia del sistema operativo." },
];

export default function AppearanceSettings() {
  const [choice, setChoice] = useState<ThemeChoice>(() => readStoredChoice());

  const pick = (value: ThemeChoice) => {
    setChoice(value);
    setTheme(value); // aplica al instante, sin re-montar la app
  };

  return (
    <div className={styles.panel}>
      <p className={styles.intro}>
        Elegí el tema de la interfaz. El cambio es inmediato y se recuerda entre sesiones.
      </p>
      <div className={styles.group} role="radiogroup" aria-label="Tema de la interfaz">
        {THEME_OPTIONS.map((opt) => (
          <label
            key={opt.value}
            className={`${styles.option} ${choice === opt.value ? styles.active : ""}`}
          >
            <input
              type="radio"
              name="stacky-theme"
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
      <p className={styles.intro}>
        Densidad de la interfaz. "Compacto" muestra más información por pantalla.
      </p>
      <DensityToggle />
    </div>
  );
}
