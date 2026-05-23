import { useState } from "react";
import FlowConfigPage from "./FlowConfigPage";
import {
  LOCKED_SECTIONS,
  OPTIONAL_SECTIONS,
  setSectionVisible,
  type OptionalSection,
} from "../services/uiSections";
import { useUiSectionsStore } from "../store/uiSectionsStore";
import styles from "./SettingsPage.module.css";

type SubTab = "flow" | "sections";

const OPTIONAL_LABELS: Record<OptionalSection, { title: string; hint: string }> = {
  pm:   { title: "📊 PM",          hint: "Tablero de Project Management y métricas de sprint." },
  logs: { title: "🔍 System Logs", hint: "Vista cruda de logs estructurados del backend." },
  docs: { title: "📄 Docs",        hint: "Navegador de documentación indexada del proyecto." },
};

const LOCKED_LABELS: Record<typeof LOCKED_SECTIONS[number], { title: string; hint: string }> = {
  team:     { title: "⚡ Mi Equipo",      hint: "Pantalla principal de operación." },
  tickets:  { title: "📋 Tickets ADO",    hint: "Tablero de tickets sincronizados con Azure DevOps." },
  settings: { title: "⚙️ Configuración", hint: "Esta misma pantalla — no puede ocultarse." },
};

function SectionsVisibilityPanel() {
  const sections = useUiSectionsStore((s) => s.sections);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<OptionalSection | null>(null);

  const toggle = async (key: OptionalSection, next: boolean) => {
    setError(null);
    setBusy(key);
    try {
      await setSectionVisible(key, next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el cambio.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={styles.sectionsPanel}>
      <p className={styles.sectionsIntro}>
        Elegí qué pestañas de la barra superior querés ver. Las marcadas como{" "}
        <span className={styles.lockedBadge}>Obligatoria</span> no se pueden ocultar.
      </p>

      {OPTIONAL_SECTIONS.map((key) => {
        const meta = OPTIONAL_LABELS[key];
        const checked = sections[key];
        const disabled = busy === key;
        return (
          <div key={key} className={styles.row}>
            <div className={styles.rowLabel}>
              <span className={styles.rowTitle}>{meta.title}</span>
              <span className={styles.rowHint}>{meta.hint}</span>
            </div>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={(e) => toggle(key, e.target.checked)}
              />
              <span className={styles.toggleSlider} />
            </label>
          </div>
        );
      })}

      {LOCKED_SECTIONS.map((key) => {
        const meta = LOCKED_LABELS[key];
        return (
          <div key={key} className={styles.row}>
            <div className={styles.rowLabel}>
              <span className={styles.rowTitle}>{meta.title}</span>
              <span className={styles.rowHint}>{meta.hint}</span>
            </div>
            <span className={styles.lockedBadge}>Obligatoria</span>
          </div>
        );
      })}

      {error && <div className={styles.errorText}>{error}</div>}
    </div>
  );
}

export default function SettingsPage() {
  const [sub, setSub] = useState<SubTab>("flow");

  return (
    <div className={styles.root}>
      <div className={styles.subTabs}>
        <button
          className={`${styles.subTab} ${sub === "flow" ? styles.active : ""}`}
          onClick={() => setSub("flow")}
        >
          Flujo
        </button>
        <button
          className={`${styles.subTab} ${sub === "sections" ? styles.active : ""}`}
          onClick={() => setSub("sections")}
        >
          Vista / Secciones
        </button>
      </div>

      <div className={styles.content}>
        {sub === "flow" && <FlowConfigPage />}
        {sub === "sections" && <SectionsVisibilityPanel />}
      </div>
    </div>
  );
}
