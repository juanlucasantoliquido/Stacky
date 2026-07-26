import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ClientProfileApi, FlowConfig, Projects } from "../api/endpoints";
import { Button, Select } from "../components/ui";
import { useWorkbench } from "../store/workbench";
import FlowConfigPage from "./FlowConfigPage";
import styles from "./StatesConfigPage.module.css";
import {
  ROLE_LABEL,
  STATE_ROLES,
  coherenceMessage,
  incoherentStatesFor,
  missingRequiredFields,
  optionsWithCurrent,
  withStatesAdded,
  type RoleStateMachine,
  type StateRole,
} from "./statesConfigModel";

/**
 * Plan 216 F2/F3 — Un solo lugar para todo lo que tiene que ver con estados.
 *
 * Antes vivía partido al medio: las reglas estado→agente en la pestaña "Flujo",
 * y la máquina de estados dentro del formulario del perfil del cliente. Eran el
 * mismo dominio y nada avisaba cuando se contradecían entre sí.
 */
export default function StatesConfigPage() {
  const activeProject = useWorkbench((s) => s.activeProject);
  const nombre = activeProject?.name ?? null;
  const qc = useQueryClient();

  const perfilQ = useQuery({
    queryKey: ["client-profile", nombre],
    queryFn: () => ClientProfileApi.get(nombre!),
    enabled: !!nombre,
    staleTime: 30_000,
  });

  const estadosQ = useQuery({
    queryKey: ["tracker-states", nombre],
    queryFn: () => Projects.trackerStates(nombre!),
    enabled: !!nombre,
    staleTime: 5 * 60_000,
  });

  const reglasQ = useQuery({
    queryKey: ["flow-config", nombre],
    queryFn: () => FlowConfig.list(nombre),
    enabled: !!nombre,
    staleTime: 30_000,
  });

  const guardar = useMutation({
    mutationFn: (maquina: Record<string, RoleStateMachine>) => {
      const perfil = perfilQ.data?.profile;
      if (!perfil || !nombre) throw new Error("Sin perfil del cliente para guardar.");
      return ClientProfileApi.save(nombre, {
        ...perfil,
        tracker_state_machine: maquina,
      } as never);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["client-profile", nombre] }),
  });

  const maquina = useMemo(
    () =>
      ((perfilQ.data?.profile as never as { tracker_state_machine?: Record<string, RoleStateMachine> })
        ?.tracker_state_machine ?? {}) as Record<string, RoleStateMachine>,
    [perfilQ.data]
  );

  const estados = estadosQ.data?.states ?? [];
  const reglas = reglasQ.data?.rules ?? [];

  function actualizarRol(rol: StateRole, parche: Partial<RoleStateMachine>) {
    guardar.mutate({ ...maquina, [rol]: { ...(maquina[rol] ?? {}), ...parche } });
  }

  return (
    <div className={styles.root}>
      <section className={styles.card}>
        <h3 className={styles.cardTitle}>¿Qué agente toma cada estado?</h3>
        <p className={styles.cardSubtitle}>
          Mapeo determinístico: estado del tracker → tipo de agente sugerido.
        </p>
        <FlowConfigPage embedded />
      </section>

      <section className={styles.card}>
        <h3 className={styles.cardTitle}>Máquina de estados del tracker</h3>
        <p className={styles.cardSubtitle}>
          Por cada rol: en qué estados actúa y a cuál mueve el ticket al terminar.
        </p>

        {!nombre && (
          <p className={styles.empty}>
            Sin proyecto activo. Seleccioná un proyecto en el TopBar para configurar los estados.
          </p>
        )}

        {nombre && !perfilQ.data?.profile && !perfilQ.isLoading && (
          <p className={styles.empty}>
            Este proyecto todavía no tiene perfil del cliente. Crealo en
            Configuración → Perfil del cliente y volvé acá.
          </p>
        )}

        {nombre && perfilQ.data?.profile && (
          <div className={styles.roles}>
            {STATE_ROLES.map((rol) => (
              <RoleCard
                key={rol}
                rol={rol}
                maquina={maquina[rol]}
                estados={estados}
                reglas={reglas}
                guardando={guardar.isPending}
                onChange={(parche) => actualizarRol(rol, parche)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function RoleCard({
  rol,
  maquina,
  estados,
  reglas,
  guardando,
  onChange,
}: {
  rol: StateRole;
  maquina: RoleStateMachine | undefined;
  estados: string[];
  reglas: { id: string; ado_state: string; agent_type: string }[];
  guardando: boolean;
  onChange: (parche: Partial<RoleStateMachine>) => void;
}) {
  const [agregando, setAgregando] = useState("");

  const incoherentes = incoherentStatesFor(rol, reglas, maquina);
  const aviso = coherenceMessage(incoherentes);
  const faltan = missingRequiredFields(maquina);

  return (
    <div className={styles.role}>
      <h4 className={styles.roleTitle}>{ROLE_LABEL[rol]}</h4>

      <div className={styles.fields}>
        <div className={styles.field}>
          <span className={styles.label}>Estados en los que actúa</span>
          <div className={styles.chips}>
            {(maquina?.input_states ?? []).map((s) => (
              <span key={s} className={styles.chip}>
                {s}
              </span>
            ))}
            {!(maquina?.input_states ?? []).length && (
              <span className={styles.label}>— ninguno —</span>
            )}
          </div>
          <Select
            value={agregando}
            disabled={guardando}
            onChange={(e) => {
              const valor = e.target.value;
              setAgregando("");
              if (valor) onChange(withStatesAdded(maquina, [valor]));
            }}
          >
            <option value="">Agregar estado…</option>
            {estados
              .filter((s) => !(maquina?.input_states ?? []).includes(s))
              .map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
          </Select>
        </div>

        <EstadoSimple
          label="Al terminar OK, mover a"
          value={maquina?.next_state_ok ?? ""}
          estados={estados}
          disabled={guardando}
          onChange={(v) => onChange({ next_state_ok: v })}
        />
        <EstadoSimple
          label="Estado de bloqueo (solo humano)"
          value={maquina?.blocked_state ?? ""}
          estados={estados}
          disabled={guardando}
          onChange={(v) => onChange({ blocked_state: v })}
        />
      </div>

      {faltan.length > 0 && (
        <p className={styles.missing}>Falta configurar: {faltan.join(", ")}.</p>
      )}

      {aviso && (
        <>
          <p className={styles.warning}>{aviso}</p>
          <div className={styles.warningActions}>
            <Button
              size="sm"
              disabled={guardando}
              onClick={() => onChange(withStatesAdded(maquina, incoherentes))}
            >
              Agregarlos a este rol
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

function EstadoSimple({
  label,
  value,
  estados,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  estados: string[];
  disabled: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <div className={styles.field}>
      <span className={styles.label}>{label}</span>
      <Select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        <option value="">— sin definir —</option>
        {optionsWithCurrent(estados, value).map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </Select>
    </div>
  );
}
