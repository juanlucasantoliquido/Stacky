/**
 * FlowConfigPage — Feature #4 (SDD-2026-05-19)
 *
 * Administración del mapeo determinístico ado_state → agent_type.
 * Permite listar, crear, editar inline y eliminar reglas.
 * Errores del backend (409 duplicado, 400 validación) se muestran inline.
 *
 * VALID_AGENT_TYPES: business | functional | technical | developer | qa
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FlowConfig } from "../api/endpoints";
import type { FlowConfigRule } from "../api/endpoints";
import styles from "./FlowConfigPage.module.css";

const VALID_AGENT_TYPES = ["business", "functional", "technical", "developer", "qa"] as const;
type ValidAgentType = (typeof VALID_AGENT_TYPES)[number];

const AGENT_LABELS: Record<ValidAgentType, string> = {
  business:   "Business",
  functional: "Functional",
  technical:  "Technical",
  developer:  "Developer",
  qa:         "QA",
};

// ── helpers ──────────────────────────────────────────────────────────────────

function extractErrorMessage(err: unknown): string {
  if (!err) return "Error desconocido";
  if (typeof err === "object" && err !== null) {
    const e = err as Record<string, unknown>;
    if (typeof e.message === "string") return e.message;
    if (typeof e.detail === "string") return e.detail;
    if (typeof e.error === "string") return e.error;
    // FastAPI/httpx response pattern
    const data = e.data as Record<string, unknown> | undefined;
    if (data && typeof data.message === "string") return data.message;
    if (data && typeof data.detail === "string") return data.detail;
  }
  return String(err);
}

// ── sub-component: CreateForm ─────────────────────────────────────────────────

interface CreateFormProps {
  onCreated: () => void;
}

function CreateForm({ onCreated }: CreateFormProps) {
  const [adoState, setAdoState] = useState("");
  const [agentType, setAgentType] = useState<ValidAgentType>("business");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => FlowConfig.create({ ado_state: adoState.trim(), agent_type: agentType }),
    onSuccess: () => {
      setAdoState("");
      setAgentType("business");
      setError(null);
      qc.invalidateQueries({ queryKey: ["flow-config"] });
      onCreated();
    },
    onError: (err) => {
      setError(extractErrorMessage(err));
    },
  });

  const canSubmit = adoState.trim().length > 0 && !mutation.isPending;

  return (
    <div className={styles.formCard}>
      <p className={styles.formTitle}>Nueva regla</p>
      <div className={styles.formRow}>
        <div className={styles.fieldGroup}>
          <label className={styles.label} htmlFor="fc-ado-state">Estado ADO</label>
          <input
            id="fc-ado-state"
            className={styles.input}
            type="text"
            placeholder="ej. New, Active, Resolved..."
            value={adoState}
            onChange={(e) => { setAdoState(e.target.value); setError(null); }}
            onKeyDown={(e) => { if (e.key === "Enter" && canSubmit) mutation.mutate(); }}
          />
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.label} htmlFor="fc-agent-type">Tipo de agente</label>
          <select
            id="fc-agent-type"
            className={styles.select}
            value={agentType}
            onChange={(e) => setAgentType(e.target.value as ValidAgentType)}
          >
            {VALID_AGENT_TYPES.map((t) => (
              <option key={t} value={t}>{AGENT_LABELS[t]}</option>
            ))}
          </select>
        </div>
        <button
          className={styles.btnPrimary}
          onClick={() => mutation.mutate()}
          disabled={!canSubmit}
        >
          {mutation.isPending ? "Guardando..." : "Agregar"}
        </button>
      </div>
      {error && <div className={styles.errorBanner}>{error}</div>}
    </div>
  );
}

// ── sub-component: RuleRow ────────────────────────────────────────────────────

interface RuleRowProps {
  rule: FlowConfigRule;
}

function RuleRow({ rule }: RuleRowProps) {
  const [editing, setEditing] = useState(false);
  const [editAdoState, setEditAdoState] = useState(rule.ado_state);
  const [editAgentType, setEditAgentType] = useState<ValidAgentType>(
    (VALID_AGENT_TYPES as readonly string[]).includes(rule.agent_type)
      ? (rule.agent_type as ValidAgentType)
      : "business"
  );
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  const updateMutation = useMutation({
    mutationFn: () =>
      FlowConfig.update(rule.id, {
        ado_state: editAdoState.trim(),
        agent_type: editAgentType,
      }),
    onSuccess: () => {
      setEditing(false);
      setError(null);
      qc.invalidateQueries({ queryKey: ["flow-config"] });
    },
    onError: (err) => {
      setError(extractErrorMessage(err));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => FlowConfig.delete(rule.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["flow-config"] });
    },
    onError: (err) => {
      setError(extractErrorMessage(err));
    },
  });

  const handleCancelEdit = () => {
    setEditing(false);
    setEditAdoState(rule.ado_state);
    setEditAgentType(
      (VALID_AGENT_TYPES as readonly string[]).includes(rule.agent_type)
        ? (rule.agent_type as ValidAgentType)
        : "business"
    );
    setError(null);
  };

  const isLoading = updateMutation.isPending || deleteMutation.isPending;

  if (editing) {
    return (
      <>
        <tr className={`${styles.tr} ${styles.trEditing}`}>
          <td className={styles.td}>
            <input
              className={styles.inlineInput}
              value={editAdoState}
              onChange={(e) => { setEditAdoState(e.target.value); setError(null); }}
              autoFocus
            />
          </td>
          <td className={styles.td}>
            <select
              className={styles.inlineSelect}
              value={editAgentType}
              onChange={(e) => setEditAgentType(e.target.value as ValidAgentType)}
            >
              {VALID_AGENT_TYPES.map((t) => (
                <option key={t} value={t}>{AGENT_LABELS[t]}</option>
              ))}
            </select>
          </td>
          <td className={styles.td} style={{ color: "rgba(255,255,255,0.3)", fontSize: 11 }}>
            {new Date(rule.updated_at).toLocaleDateString()}
          </td>
          <td className={styles.tdActions}>
            <button
              className={styles.btnIcon}
              onClick={() => updateMutation.mutate()}
              disabled={isLoading || editAdoState.trim().length === 0}
              title="Guardar"
            >
              {updateMutation.isPending ? "..." : "Guardar"}
            </button>
            <button
              className={styles.btnIcon}
              onClick={handleCancelEdit}
              disabled={isLoading}
              title="Cancelar"
            >
              Cancelar
            </button>
          </td>
        </tr>
        {error && (
          <tr>
            <td colSpan={4} className={styles.td}>
              <div className={styles.errorBanner}>{error}</div>
            </td>
          </tr>
        )}
      </>
    );
  }

  return (
    <tr className={styles.tr}>
      <td className={styles.td}>{rule.ado_state}</td>
      <td className={styles.td}>
        <span className={styles.badge}>{rule.agent_type}</span>
      </td>
      <td className={styles.td} style={{ color: "rgba(255,255,255,0.3)", fontSize: 11 }}>
        {new Date(rule.updated_at).toLocaleDateString()}
      </td>
      <td className={styles.tdActions}>
        <button
          className={styles.btnIcon}
          onClick={() => setEditing(true)}
          disabled={isLoading}
          title="Editar"
        >
          Editar
        </button>
        <button
          className={`${styles.btnIcon} ${styles.btnIconDanger}`}
          onClick={() => {
            if (window.confirm(`Eliminar regla "${rule.ado_state} → ${rule.agent_type}"?`)) {
              deleteMutation.mutate();
            }
          }}
          disabled={isLoading}
          title="Eliminar"
        >
          {deleteMutation.isPending ? "..." : "Eliminar"}
        </button>
      </td>
    </tr>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function FlowConfigPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["flow-config"],
    queryFn: () => FlowConfig.list(),
    staleTime: 30_000,
  });

  const rules = data?.rules ?? [];

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>Config de Flujo</h2>
        <p className={styles.subtitle}>
          Mapeo determinístico: estado ADO → tipo de agente sugerido.
          Clave usada: <code>agent_type</code>.
        </p>
      </div>

      <CreateForm onCreated={() => {}} />

      <div className={styles.tableCard}>
        <div className={styles.tableHeader}>
          <span className={styles.tableTitle}>Reglas activas</span>
          <span className={styles.tableCount}>{rules.length} regla{rules.length !== 1 ? "s" : ""}</span>
        </div>

        {isLoading && <div className={styles.loading}>Cargando...</div>}

        {error && (
          <div className={styles.empty}>
            Error al cargar reglas: {extractErrorMessage(error)}
          </div>
        )}

        {!isLoading && !error && rules.length === 0 && (
          <div className={styles.empty}>
            No hay reglas configuradas. Agrega una arriba.
          </div>
        )}

        {!isLoading && !error && rules.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Estado ADO</th>
                <th className={styles.th}>Tipo de agente</th>
                <th className={styles.th}>Actualizado</th>
                <th className={styles.th} style={{ textAlign: "right" }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <RuleRow key={rule.id} rule={rule} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
