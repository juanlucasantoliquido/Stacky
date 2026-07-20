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
import { FlowConfig, Projects } from "../api/endpoints";
import type { FlowConfigRule, FlowConfigListResponse } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { useConfirm } from "../components/ui";
import { scheduleUndoable } from "../services/undoManager";
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
  trackerStates: string[];
  loadingStates: boolean;
  usedStates: Set<string>;
  activeProjectName: string | null;
}

function CreateForm({ onCreated, trackerStates, loadingStates, usedStates, activeProjectName }: CreateFormProps) {
  const availableStates = trackerStates.filter((s) => !usedStates.has(s));
  const [adoState, setAdoState] = useState<string>(availableStates[0] ?? "");
  const [agentType, setAgentType] = useState<ValidAgentType>("business");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  // Mantener el select sincronizado con la lista filtrada si cambia (ej. al crear/borrar reglas).
  if (adoState && !availableStates.includes(adoState) && availableStates.length > 0) {
    setAdoState(availableStates[0]);
  }
  if (!adoState && availableStates.length > 0) {
    setAdoState(availableStates[0]);
  }

  const mutation = useMutation({
    mutationFn: () => FlowConfig.create({
      ado_state: adoState.trim(),
      agent_type: agentType,
      project: activeProjectName,
    }),
    onSuccess: () => {
      setAdoState("");
      setAgentType("business");
      setError(null);
      qc.invalidateQueries({ queryKey: ["flow-config", activeProjectName] });
      onCreated();
    },
    onError: (err) => {
      setError(extractErrorMessage(err));
    },
  });

  const noProject = !activeProjectName;
  const noStates = !loadingStates && trackerStates.length === 0;
  const allUsed = !loadingStates && trackerStates.length > 0 && availableStates.length === 0;
  const canSubmit =
    adoState.trim().length > 0 && !mutation.isPending && !noProject && !noStates && !allUsed;

  return (
    <div className={styles.formCard}>
      <p className={styles.formTitle}>Nueva regla</p>
      <div className={styles.formRow}>
        <div className={styles.fieldGroup}>
          <label className={styles.label} htmlFor="fc-ado-state">Estado ADO</label>
          <select
            id="fc-ado-state"
            className={styles.select}
            value={adoState}
            onChange={(e) => { setAdoState(e.target.value); setError(null); }}
            disabled={noProject || loadingStates || noStates || allUsed}
          >
            {loadingStates && <option value="">Cargando estados…</option>}
            {!loadingStates && noProject && <option value="">Sin proyecto activo</option>}
            {!loadingStates && noStates && <option value="">No hay estados disponibles</option>}
            {!loadingStates && allUsed && <option value="">Todos los estados ya tienen regla</option>}
            {!loadingStates && availableStates.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
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
  trackerStates: string[];
  otherUsedStates: Set<string>; // estados ocupados por otras reglas (excluye el propio)
  activeProjectName: string | null;
}

function RuleRow({ rule, trackerStates, otherUsedStates, activeProjectName }: RuleRowProps) {
  const [editing, setEditing] = useState(false);
  const [editAdoState, setEditAdoState] = useState(rule.ado_state);
  const [editAgentType, setEditAgentType] = useState<ValidAgentType>(
    (VALID_AGENT_TYPES as readonly string[]).includes(rule.agent_type)
      ? (rule.agent_type as ValidAgentType)
      : "business"
  );
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();
  const ask = useConfirm();

  const updateMutation = useMutation({
    mutationFn: () =>
      FlowConfig.update(rule.id, {
        ado_state: editAdoState.trim(),
        agent_type: editAgentType,
        project: activeProjectName,
      }),
    onSuccess: () => {
      setEditing(false);
      setError(null);
      qc.invalidateQueries({ queryKey: ["flow-config", activeProjectName] });
    },
    onError: (err) => {
      setError(extractErrorMessage(err));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => FlowConfig.delete(rule.id, activeProjectName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["flow-config", activeProjectName] });
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
    // Opciones disponibles: estados del tracker que no estén ocupados por OTRAS reglas
    // + el estado actual de esta regla (para no autoexcluirse).
    const selectableStates = trackerStates.filter(
      (s) => !otherUsedStates.has(s) || s === rule.ado_state
    );
    // Si el estado actual no está en el tracker (por ejemplo, regla creada antes del dropdown),
    // lo incluimos como opción para permitir editarlo sin perderlo.
    if (!selectableStates.includes(editAdoState) && editAdoState) {
      selectableStates.unshift(editAdoState);
    }
    return (
      <>
        <tr className={`${styles.tr} ${styles.trEditing}`}>
          <td className={styles.td}>
            <select
              className={styles.inlineSelect}
              value={editAdoState}
              onChange={(e) => { setEditAdoState(e.target.value); setError(null); }}
              autoFocus
            >
              {selectableStates.length === 0 && <option value="">Sin estados disponibles</option>}
              {selectableStates.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
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
            // Plan 185 — undo con gracia (reemplaza la confirmación previa).
            // Quitamos la regla del cache de forma OPTIMISTA y DIFERIMOS el
            // DELETE real (config LOCAL del dashboard, no remoto) 6 s con un toast
            // "Deshacer" (o Ctrl+Z). Undo restaura el cache y nunca llama al
            // backend; si la gracia expira, se commitea garantizado.
            const key = ["flow-config", activeProjectName];
            const prevData = qc.getQueryData<FlowConfigListResponse>(key);
            qc.setQueryData<FlowConfigListResponse>(key, (old) =>
              old ? { ...old, rules: old.rules.filter((r) => r.id !== rule.id) } : old
            );
            scheduleUndoable({
              id: `flow-rule:${rule.id}`,
              label: `Regla "${rule.ado_state} → ${rule.agent_type}" eliminada`,
              commit: async () => {
                await FlowConfig.delete(rule.id, activeProjectName);
                qc.invalidateQueries({ queryKey: key });
              },
              onUndo: () => qc.setQueryData<FlowConfigListResponse>(key, prevData),
              onError: (err) => {
                qc.setQueryData<FlowConfigListResponse>(key, prevData); // rechazó ⇒ restaurar
                setError(extractErrorMessage(err));
              },
            });
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
  const activeProject = useWorkbench((s) => s.activeProject);
  const activeProjectName = activeProject?.name ?? null;

  const { data, isLoading, error } = useQuery({
    queryKey: ["flow-config", activeProjectName],
    queryFn: () => FlowConfig.list(activeProjectName),
    staleTime: 30_000,
  });

  const trackerStatesQuery = useQuery({
    queryKey: ["tracker-states", activeProject?.name],
    queryFn: () => Projects.trackerStates(activeProject!.name),
    enabled: !!activeProject,
    staleTime: 5 * 60_000,
  });

  const rules = data?.rules ?? [];
  const trackerStates = trackerStatesQuery.data?.states ?? [];
  const usedStates = new Set(rules.map((r) => r.ado_state));

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>Config de Flujo</h2>
        <p className={styles.subtitle}>
          Mapeo determinístico: estado ADO → tipo de agente sugerido.
          Clave usada: <code>agent_type</code>.
        </p>
      </div>

      {!activeProject && (
        <div className={styles.empty} style={{ marginBottom: 16 }}>
          Sin proyecto activo. Seleccioná un proyecto en el TopBar para ver los estados ADO disponibles.
        </div>
      )}

      <CreateForm
        onCreated={() => {}}
        trackerStates={trackerStates}
        loadingStates={trackerStatesQuery.isLoading}
        usedStates={usedStates}
        activeProjectName={activeProjectName}
      />

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
              {rules.map((rule) => {
                const otherUsedStates = new Set(
                  rules.filter((r) => r.id !== rule.id).map((r) => r.ado_state)
                );
                return (
                  <RuleRow
                    key={rule.id}
                    rule={rule}
                    trackerStates={trackerStates}
                    otherUsedStates={otherUsedStates}
                    activeProjectName={activeProjectName}
                  />
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
