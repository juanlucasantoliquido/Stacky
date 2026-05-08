import React from "react";
import styles from "./AgentWorkflowForm.module.css";

export interface AgentWorkflowFormValue {
  allowed_states: string[];
  transition_state: string;
  requires_prior_output: boolean;
}

interface AgentWorkflowFormProps {
  value: AgentWorkflowFormValue;
  onChange: (v: AgentWorkflowFormValue) => void;
  trackerStates: string[];
  loadingStates?: boolean;
  loadError?: boolean;
  projectDisplayName?: string;
}

export default function AgentWorkflowForm({
  value,
  onChange,
  trackerStates,
  loadingStates = false,
  loadError = false,
  projectDisplayName,
}: AgentWorkflowFormProps) {
  function toggleState(state: string) {
    const next = value.allowed_states.includes(state)
      ? value.allowed_states.filter((s) => s !== state)
      : [...value.allowed_states, state];
    onChange({ ...value, allowed_states: next });
  }

  function selectAll() {
    onChange({ ...value, allowed_states: [...trackerStates] });
  }

  function clearAll() {
    onChange({ ...value, allowed_states: [] });
  }

  return (
    <div className={styles.root}>
      {/* ─── Estados visibles ──────────────────────────────────── */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.label}>
            Estados visibles
            {projectDisplayName && (
              <span className={styles.labelMeta}> en {projectDisplayName}</span>
            )}
          </span>
          {trackerStates.length > 0 && (
            <div className={styles.bulkActions}>
              <button type="button" className={styles.bulkBtn} onClick={selectAll}>
                Seleccionar todos
              </button>
              <button type="button" className={styles.bulkBtn} onClick={clearAll}>
                Limpiar
              </button>
            </div>
          )}
        </div>

        {loadingStates ? (
          <p className={styles.hint}>Cargando estados del tracker…</p>
        ) : loadError ? (
          <p className={styles.hintError}>No se pudieron cargar los estados del tracker.</p>
        ) : trackerStates.length === 0 ? (
          <p className={styles.hint}>
            Sin estados disponibles. Configurá las credenciales del proyecto para cargarlos automáticamente.
          </p>
        ) : (
          <div className={styles.chips}>
            {trackerStates.map((s) => {
              const active = value.allowed_states.includes(s);
              return (
                <button
                  key={s}
                  type="button"
                  className={active ? styles.chipActive : styles.chip}
                  onClick={() => toggleState(s)}
                >
                  {active ? "✓ " : ""}{s}
                </button>
              );
            })}
          </div>
        )}

        {value.allowed_states.length === 0 && trackerStates.length > 0 && (
          <p className={styles.hintMuted}>Sin selección = ve todos los estados.</p>
        )}
      </div>

      {/* ─── Estado de transición ──────────────────────────────── */}
      <div className={styles.section}>
        <span className={styles.label}>Estado de transición al terminar</span>
        {!loadingStates && trackerStates.length > 0 ? (
          <select
            className={styles.select}
            value={value.transition_state}
            onChange={(e) => onChange({ ...value, transition_state: e.target.value })}
          >
            <option value="">— Sin transición automática —</option>
            {trackerStates.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        ) : (
          <input
            className={styles.input}
            type="text"
            placeholder="Ej: In Progress"
            value={value.transition_state}
            onChange={(e) => onChange({ ...value, transition_state: e.target.value })}
          />
        )}
      </div>

      {/* ─── Requires prior output ─────────────────────────────── */}
      <div className={styles.section}>
        <label className={styles.checkboxLabel}>
          <input
            type="checkbox"
            className={styles.checkbox}
            checked={value.requires_prior_output}
            onChange={(e) => onChange({ ...value, requires_prior_output: e.target.checked })}
          />
          Requiere output previo antes de ejecutar este empleado
        </label>
      </div>
    </div>
  );
}
