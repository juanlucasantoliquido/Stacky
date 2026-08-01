import React, { useCallback, useEffect, useState } from "react";

import { PipelineCopilot, type PipelineCopilotSessionDTO } from "../../api/endpoints";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";
import { Button, SectionHeader } from "../ui";
import {
  SESSION_STATES,
  availableActionIds,
  mustShowUndoHint,
  needsOperatorConfirmation,
  stateLabel,
  type SessionState,
} from "./pipelineCopilotModel";
import styles from "./PipelineCopilotSection.module.css";

/**
 * Plan 279 F8 — El copiloto de pipelines: un solo hilo conversacional.
 *
 * CASCARON de presentacion a proposito: el repo no tiene RTL ni jsdom, asi que
 * TODA la logica testeable vive en pipelineCopilotModel.ts (8 casos verdes) y
 * en el backend (services/pipeline_session.py, 11 casos verdes). Aca solo se
 * pinta el estado y se ofrecen las acciones que el modelo declara.
 *
 * Rieles que este componente NO puede romper:
 *  - Human-in-the-loop: la escritura solo se ofrece en 'confirm', y ANTES se le
 *    muestra al operador como deshacerla (undo_hint). Nunca se autoconfirma.
 *  - El valor de un secreto jamas se muestra ni se pide: solo NOMBRES.
 *  - El gate de la flag lo hace el shell por `healthKey`, no este componente.
 */
export const PipelineCopilotSection: React.FC<{ ctx: DevOpsSectionContext }> = ({ ctx }) => {
  // `conversation_id` del hilo del agente DevOps. El shell todavia no lo propaga
  // (DevOpsSectionContext no lo declara), asi que mientras sea null la seccion
  // explica que hacer en vez de fingir un estado.
  const [conversationId] = useState<number | null>(null);
  const [session, setSession] = useState<PipelineCopilotSessionDTO | null>(null);
  const [undoHint, setUndoHint] = useState<string>("");
  const [unavailable, setUnavailable] = useState<{ ids: string[]; reason: string }>({
    ids: [],
    reason: "",
  });
  const [cargando, setCargando] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  const cargar = useCallback(async (id: number) => {
    setCargando(true);
    setError("");
    try {
      const resp = await PipelineCopilot.session(id);
      setSession(resp.session);
      setUnavailable({
        ids: resp.unavailable_actions ?? [],
        reason: resp.unavailable_reason ?? "",
      });
      const hint = await PipelineCopilot.undoHint(id);
      setUndoHint(hint.undo_hint ?? "");
    } catch (e) {
      // Estado de error EXPLICITO: nunca se deja la pantalla en blanco fingiendo
      // que no paso nada (la sesion sigue viva en el backend).
      setError(e instanceof Error ? e.message : "No se pudo leer la sesión del copiloto.");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    if (conversationId !== null) void cargar(conversationId);
  }, [conversationId, cargar]);

  const estado = (session?.state ?? "intake") as SessionState;
  const acciones = availableActionIds(estado);
  const mostrarDeshacer = mustShowUndoHint(estado) && undoHint !== "";

  const claseDePaso = (s: SessionState): string => {
    if (s !== estado) return styles.paso;
    if (s === "committed") return `${styles.paso} ${styles.pasoTerminal}`;
    if (s === "failed") return `${styles.paso} ${styles.pasoFallido}`;
    return `${styles.paso} ${styles.pasoActivo}`;
  };

  return (
    <div className={styles.wrap}>
      <SectionHeader
        title="Copiloto de pipelines"
        subtitle="Describí lo que necesitás y el copiloto arma, valida y explica la pipeline sin que salgas de acá."
      />

      {/* Progreso: los 8 pasos, siempre visibles, con el actual resaltado. */}
      <div className={styles.pasos}>
        {SESSION_STATES.map((s) => (
          <span key={s} className={claseDePaso(s)}>
            {stateLabel(s)}
          </span>
        ))}
      </div>

      {conversationId === null && (
        <div className={styles.panel}>
          <span className={styles.titulo}>Todavía no hay un hilo abierto</span>
          <p className={styles.ayuda}>
            El copiloto trabaja sobre un hilo del Agente DevOps. Abrí uno en la sección
            «Agente DevOps» y volvé acá: la sesión se retoma sola, en el paso donde quedó.
          </p>
          <div className={styles.acciones}>
            <Button
              variant="secondary"
              onClick={() => ctx.setActiveSection?.("agente")}
              disabled={!ctx.setActiveSection}
            >
              Ir al Agente DevOps
            </Button>
          </div>
        </div>
      )}

      {cargando && <div className={styles.aviso}>Leyendo la sesión…</div>}

      {error !== "" && (
        <div className={styles.error}>
          {error}
          <div className={styles.acciones}>
            <Button
              variant="secondary"
              onClick={() => conversationId !== null && void cargar(conversationId)}
            >
              Reintentar
            </Button>
          </div>
        </div>
      )}

      {/* [C6] Degradación honesta: si falta una flag PREEXISTENTE, se dice CUÁL,
          en vez de morir después en un 404 mudo. */}
      {unavailable.reason !== "" && (
        <div className={styles.aviso}>
          Estos pasos no están disponibles porque falta activar{" "}
          <strong>{unavailable.reason}</strong> (Configuración → Arnés):{" "}
          {unavailable.ids.join(", ")}.
        </div>
      )}

      {session !== null && (
        <div className={styles.panel}>
          <span className={styles.titulo}>{stateLabel(estado)}</span>

          {session.open_questions.length > 0 && (
            <p className={styles.ayuda}>{session.open_questions[0]}</p>
          )}

          {/* Solo NOMBRES de variables. Ningún valor llega nunca a esta pantalla. */}
          {session.missing_variables.length > 0 && (
            <>
              <p className={styles.ayuda}>
                Faltan estas variables (se cargan en la sección «Variables»; acá solo se
                nombran, nunca se muestran sus valores):
              </p>
              <ul className={styles.variables}>
                {session.missing_variables.map((v) => (
                  <li key={v}>{v}</li>
                ))}
              </ul>
            </>
          )}

          {session.state === "failed" && session.failure_reason !== "" && (
            <div className={styles.error}>La sesión se detuvo: {session.failure_reason}</div>
          )}

          {/* [ADICIÓN ARQUITECTO] El deshacer se muestra ANTES de confirmar. */}
          {mostrarDeshacer && (
            <div className={styles.deshacer}>
              <span className={styles.deshacerTitulo}>Si esto sale mal, así lo deshacés</span>
              {undoHint}
            </div>
          )}

          <p className={styles.ayuda}>
            {needsOperatorConfirmation(estado)
              ? "Nada se escribe hasta que confirmes. Revisá el deshacer de arriba antes de seguir."
              : "Ninguno de estos pasos escribe nada en tu repositorio."}
          </p>

          <div className={styles.acciones}>
            {acciones.map((id) => (
              <Button key={id} variant="secondary" disabled={unavailable.ids.includes(id)}>
                {id}
              </Button>
            ))}
          </div>
        </div>
      )}

    </div>
  );
};
