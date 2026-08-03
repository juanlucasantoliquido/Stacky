import React, { useCallback, useEffect, useState } from "react";

import {
  DevOpsAgentApi,
  PipelineCopilot,
  type PipelineCopilotSessionDTO,
} from "../../api/endpoints";
import { userFacingMessage } from "../../api/gatewayError";
import type { DevOpsSectionContext } from "../../pages/DevOpsPage";
import { useWorkbench } from "../../store/workbench";
import AgentRuntimeSelector from "../AgentRuntimeSelector";
import type { AgentRuntime } from "../../types";
import { Button, SectionHeader, Textarea } from "../ui";
import { DevOpsActionConsole } from "./DevOpsActionConsole";
import {
  SESSION_STATES,
  availableActionIds,
  copilotStartBody,
  missingWriteFlags,
  mustShowUndoHint,
  needsOperatorConfirmation,
  pickCopilotConversation,
  resolveCopilotTarget,
  stateLabel,
  type CopilotTarget,
  type SessionState,
} from "./pipelineCopilotModel";
import styles from "./PipelineCopilotSection.module.css";

/**
 * Plan 279 F8 — El copiloto de pipelines: un solo hilo conversacional.
 * Plan 288 — el copiloto se USA: arranca su propio hilo, LOCAL, y el destino
 *            de la escritura lo decide el proyecto.
 *
 * CASCARON de presentacion a proposito: el repo no tiene RTL ni jsdom, asi que
 * TODA la logica testeable vive en pipelineCopilotModel.ts (13 casos verdes) y
 * en el backend (services/pipeline_session.py + api/pipeline_copilot.py). Aca
 * solo se pinta el estado y se ofrecen las acciones que el modelo declara.
 *
 * Rieles que este componente NO puede romper:
 *  - Human-in-the-loop: la escritura solo se ofrece en 'confirm', y ANTES se le
 *    muestra al operador como deshacerla (undo_hint). Nunca se autoconfirma. La
 *    confirmacion real la hace DevOpsActionConsole via confirmGateway: NO hay
 *    un segundo mecanismo de confirmacion en esta seccion.
 *  - El valor de un secreto jamas se muestra ni se pide: solo NOMBRES.
 *  - El gate de la flag lo hace el shell por `healthKey`, no este componente.
 *  - CERO servidor remoto: `copilotStartBody` NO manda `server_alias`, que es
 *    lo unico que ata un turno a un host (api/devops_agent.py:144-149).
 */
export const PipelineCopilotSection: React.FC<{ ctx: DevOpsSectionContext }> = ({ ctx }) => {
  const activeProject = useWorkbench((s) => s.activeProject);
  const project = activeProject?.name ?? "";

  const [conversationId, setConversationId] = useState<number | null>(null);
  const [session, setSession] = useState<PipelineCopilotSessionDTO | null>(null);
  const [target, setTarget] = useState<CopilotTarget | null>(null);
  const [undoHint, setUndoHint] = useState<string>("");
  const [unavailable, setUnavailable] = useState<{ ids: string[]; reason: string }>({
    ids: [],
    reason: "",
  });
  const [cargando, setCargando] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [pedido, setPedido] = useState<string>("");
  const [runtime, setRuntime] = useState<AgentRuntime>("claude_code_cli");
  const [arrancando, setArrancando] = useState<boolean>(false);
  const [aviso, setAviso] = useState<string>("");

  const cargar = useCallback(async (id: number) => {
    setCargando(true);
    setError("");
    try {
      const resp = await PipelineCopilot.session(id);
      setSession(resp.session);
      setTarget(resolveCopilotTarget(resp));
      setUnavailable({
        ids: resp.unavailable_actions ?? [],
        reason: resp.unavailable_reason ?? "",
      });
      const hint = await PipelineCopilot.undoHint(id);
      setUndoHint(hint.undo_hint ?? "");
    } catch (e) {
      // Estado de error EXPLICITO: nunca se deja la pantalla en blanco fingiendo
      // que no paso nada (la sesion sigue viva en el backend). Plan 288: el
      // texto pasa por userFacingMessage (plan 273 F4), nunca `e.message` crudo.
      setError(userFacingMessage(e).title);
    } finally {
      setCargando(false);
    }
  }, []);

  /** Plan 288 — cumple lo que la seccion promete: la sesion se retoma sola. */
  const retomar = useCallback(async () => {
    if (!project) return;
    try {
      const lista = await DevOpsAgentApi.list(project);
      const id = pickCopilotConversation(lista.conversations);
      if (id !== null) {
        setConversationId(id);
        await cargar(id);
      }
    } catch {
      // Silencioso a proposito: no poder retomar no es un error del operador,
      // simplemente todavia no hay hilo y se le ofrece abrir uno.
    }
  }, [project, cargar]);

  useEffect(() => {
    void retomar();
  }, [retomar]);

  const empezar = useCallback(async () => {
    const texto = pedido.trim();
    if (!project || !texto) return;
    setArrancando(true);
    setError("");
    setAviso("");
    try {
      const res = await DevOpsAgentApi.start(
        copilotStartBody({ project, message: texto, runtime }),
      );
      if (res.mode === "deterministic" || typeof res.conversation_id !== "number") {
        // GitHub Copilot no tiene turno CLI: el backend lo declara y el
        // operador conserva la capacidad completa por el motor determinista.
        setAviso(
          res.detail ??
            "Con GitHub Copilot el copiloto usa el motor determinista: escribí lo que " +
              "necesitás en la consola de acciones de acá abajo.",
        );
        return;
      }
      setPedido("");
      setConversationId(res.conversation_id);
      await cargar(res.conversation_id);
    } catch (e) {
      setError(userFacingMessage(e).title);
    } finally {
      setArrancando(false);
    }
  }, [project, pedido, runtime, cargar]);

  const estado = (session?.state ?? "intake") as SessionState;
  const acciones = availableActionIds(estado);
  const mostrarDeshacer = mustShowUndoHint(estado) && undoHint !== "";
  const flagsDeEscritura = missingWriteFlags(ctx.health);

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

      {/* Plan 288 — el destino que DECLARA el proyecto, dicho antes de escribir
          nada. Si el proyecto no lo declara se dice, en vez de caer en ADO. */}
      {target !== null && (
        <div
          className={
            target.blocked ? `${styles.destino} ${styles.destinoFalta}` : styles.destino
          }
        >
          {target.blocked ? (
            target.message
          ) : (
            <>
              Destino según el proyecto <strong>{project}</strong>:{" "}
              <span className={styles.destinoArchivo}>
                {target.provider === "ado" ? "Azure DevOps" : "GitLab"} — {target.file}
              </span>
            </>
          )}
        </div>
      )}

      {/* Plan 288 — el arranque LOCAL. Antes esta rama era un callejón sin
          salida: mandaba al operador a «Agente DevOps» y el copiloto nunca se
          enteraba del hilo. Ahora abre el suyo, acá, sin servidor remoto. */}
      {conversationId === null && (
        <div className={styles.panel}>
          <span className={styles.titulo}>Contame qué pipeline necesitás</span>
          <p className={styles.ayuda}>
            Escribilo en castellano. El copiloto corre <strong>local</strong>, sobre el
            repositorio del proyecto activo: no hace falta ningún servidor ni agente
            remoto configurado.
          </p>
          {project === "" && (
            <div className={styles.error}>
              No hay proyecto activo. Elegí uno arriba y volvé: el copiloto necesita saber
              sobre qué repositorio trabaja.
            </div>
          )}
          <AgentRuntimeSelector value={runtime} onChange={setRuntime} disabled={arrancando} />
          <Textarea
            className={styles.pedido}
            value={pedido}
            onChange={(e) => setPedido(e.target.value)}
            placeholder="Ej.: necesito una pipeline que compile el backend, corra los tests y publique el artefacto."
            disabled={arrancando || project === ""}
          />
          <div className={styles.acciones}>
            <Button
              variant="primary"
              onClick={() => void empezar()}
              disabled={arrancando || project === "" || pedido.trim() === ""}
            >
              {arrancando ? "Abriendo el hilo…" : "Empezar"}
            </Button>
          </div>
        </div>
      )}

      {cargando && <div className={styles.aviso}>Leyendo la sesión…</div>}

      {aviso !== "" && <div className={styles.aviso}>{aviso}</div>}

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

      {/* Plan 288 — degradación honesta del PASO FINAL: las 2 flags que habilitan
          la escritura nacen OFF (escriben en el repo real). Decirlo al principio
          evita que el operador recorra los 8 pasos para chocarse al final. */}
      {flagsDeEscritura.length > 0 && (
        <div className={styles.aviso}>
          El copiloto puede armar, revisar y explicarte la pipeline, pero todavía no
          puede <strong>crearla</strong> en el repositorio: falta activar{" "}
          {flagsDeEscritura.join(" y ")} (Configuración → Arnés, categoría DevOps).
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

          {/* Plan 288 — antes esto eran botones SIN onClick: prometían una acción
              que no ocurría. Ahora son etiquetas de lo que el paso habilita; la
              ejecución (con su confirmación) vive en la consola de abajo, que es
              el ÚNICO mecanismo de confirmación del panel (D1). */}
          <p className={styles.ayuda}>
            En este paso el copiloto puede proponerte:
          </p>
          <div className={styles.acciones}>
            {acciones.map((id) => (
              <span
                key={id}
                className={
                  unavailable.ids.includes(id) ? `${styles.chip} ${styles.chipApagado}` : styles.chip
                }
              >
                {id}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Plan 288 — el lugar donde el pedido en castellano se vuelve una acción
          tipada con su tarjeta de confirmación. Es el MISMO componente que ya
          usa «Agente DevOps» (plan 267 F6): cero mecanismos nuevos. */}
      <DevOpsActionConsole
        enabled={ctx.health.action_nl_enabled === true}
        project={project}
        onNavigate={(path) => {
          window.location.hash = path;
        }}
      />
    </div>
  );
};
