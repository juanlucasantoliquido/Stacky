/**
 * ClientProfileCopilotPanel.tsx — Plan 296 F6.
 *
 * CASCARON DE PRESENTACION. Toda la logica testeable vive en
 * clientProfileCopilotModel.ts (el repo NO tiene RTL ni jsdom).
 *
 * REGLA DURA (C14): CERO estilos inline en este archivo. Todo por className
 * desde el .module.css. uiDebtRatchet.test.ts congela la cantidad por archivo y
 * la deuda solo puede BAJAR.
 *
 * OJO: este comentario NO puede escribir el literal que el gate busca. Un
 * comentario que NOMBRA el patron rompe el gate por grep (gotcha de la casa con
 * 7 ocurrencias registradas antes de esta).
 *
 * REGLA DE UI INNEGOCIABLE: un control que no se puede usar se DESHABILITA CON
 * EL MOTIVO A LA VISTA; nunca se esconde.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  ProfileCopilotApi,
  type ProfileCopilotFicha,
  type ProfileCopilotPatch,
  type ProfileCopilotPregunta,
} from "../api/endpoints";
import styles from "./ClientProfileCopilotPanel.module.css";
import {
  accionesDisponibles,
  motivoAplicarInvalido,
  motivoRuntimeNoDisponible,
  progresoTexto,
  puedeElegirRuntime,
  runtimeLabel,
  stateLabel,
  type ProfileSessionState,
} from "./clientProfileCopilotModel";

const ETIQUETA_ACCION: Record<string, string> = {
  responder: "Responder",
  proponer: "Ver los cambios propuestos",
  aplicar: "Aplicar los cambios",
  cambiar_runtime: "Cambiar de motor",
};

type Props = {
  projectName: string;
  /** Invalidacion de la cache del perfil, que ClientProfileEditor ya resuelve. */
  onProfileChanged: () => void;
};

export default function ClientProfileCopilotPanel({ projectName, onProfileChanged }: Props) {
  // C20 — la flag OFF cuesta UN request por sesion de pantalla, no uno por render.
  const runtimesQuery = useQuery({
    queryKey: ["profile-copilot", "runtimes"],
    queryFn: () => ProfileCopilotApi.runtimes(),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const [session, setSession] = useState<Record<string, unknown> | null>(null);
  const [pregunta, setPregunta] = useState<ProfileCopilotPregunta | null>(null);
  const [respuesta, setRespuesta] = useState("");
  const [mensaje, setMensaje] = useState("");
  const [advertencia, setAdvertencia] = useState("");
  const [patch, setPatch] = useState<ProfileCopilotPatch | null>(null);
  const [motivoInvalido, setMotivoInvalido] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const stateQuery = useQuery({
    queryKey: ["profile-copilot", "state", projectName],
    queryFn: () => ProfileCopilotApi.state(projectName),
    staleTime: 60 * 1000,
    retry: false,
  });

  const fichas: ProfileCopilotFicha[] = useMemo(
    () => runtimesQuery.data?.data?.runtimes ?? [],
    [runtimesQuery.data]
  );

  // Con la flag maestra apagada el endpoint da 404: el panel NO se monta y
  // ClientProfileEditor se renderiza byte a byte como antes del plan.
  if (runtimesQuery.isLoading) return null;
  if (!runtimesQuery.data?.ok) return null;

  const estadoSesion = String(session?.state ?? "eleccion_runtime") as ProfileSessionState;
  const runtimeElegido = String(session?.runtime_elegido ?? "");
  const completitud = stateQuery.data?.data?.completitud;
  const applyHabilitado = !motivoInvalido;
  const acciones = accionesDisponibles(estadoSesion, applyHabilitado);

  const turno = async (body: Record<string, unknown>) => {
    setOcupado(true);
    try {
      const res = await ProfileCopilotApi.turn(projectName, { session, ...body });
      if (res.ok && res.data) {
        setSession(res.data.session);
        setPregunta(res.data.pregunta);
        setMensaje(res.data.mensaje);
        setAdvertencia(res.data.advertencia);
        setRespuesta("");
      } else {
        setAdvertencia(res.errorBody?.error ?? "No se pudo avanzar la conversación.");
      }
    } finally {
      setOcupado(false);
    }
  };

  const proponer = async () => {
    setOcupado(true);
    try {
      const res = await ProfileCopilotApi.propose(projectName, { session });
      if (res.ok && res.data) {
        setPatch(res.data.patch);
        setMotivoInvalido(motivoAplicarInvalido(res.data.validacion_previa));
      } else {
        setAdvertencia(res.errorBody?.error ?? "No se pudo armar la propuesta.");
      }
    } finally {
      setOcupado(false);
    }
  };

  const aplicar = async () => {
    if (!patch) return;
    setOcupado(true);
    try {
      const res = await ProfileCopilotApi.apply(projectName, {
        session,
        patch,
        confirm_token: patch.confirm_token,
        confirmaciones_sensibles: patch.sensibles,
      });
      if (res.ok && res.data) {
        setSession(res.data.session);
        setPatch(null);
        setMensaje(`Listo: se aplicaron ${res.data.aplicados} cambios al perfil.`);
        onProfileChanged();
      } else {
        setAdvertencia(res.errorBody?.message ?? res.errorBody?.error ?? "No se pudo aplicar.");
      }
    } finally {
      setOcupado(false);
    }
  };

  const ejecutar = (id: string) => {
    if (id === "responder") return turno({ respuesta });
    if (id === "proponer") return proponer();
    if (id === "aplicar") return aplicar();
    return undefined;
  };

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h4 className={styles.title}>Configurar el perfil conversando</h4>
        <span className={styles.step}>{stateLabel(estadoSesion)}</span>
      </div>

      <p className={styles.intro}>
        Te pregunto en castellano lo que falta, deduzco lo que ya existe y te muestro
        los cambios <strong>antes</strong> de aplicarlos. Primero elegí con qué motor
        querés trabajar: Stacky recomienda, nunca elige por vos.
      </p>

      {completitud ? (
        <div className={styles.progress}>
          {progresoTexto(completitud)} — {completitud.porcentaje}%
          {completitud.listo_para_usar ? " · el perfil ya sirve" : " · todavía falta"}
        </div>
      ) : null}

      <div className={styles.runtimeGrid}>
        {fichas.map((ficha) => {
          const id = String(ficha.runtime);
          const motivo = motivoRuntimeNoDisponible(ficha);
          const seleccionado = id === runtimeElegido;
          return (
            <button
              key={id}
              type="button"
              className={
                seleccionado
                  ? `${styles.runtimeCard} ${styles.runtimeCardSelected}`
                  : styles.runtimeCard
              }
              disabled={ocupado || !puedeElegirRuntime(estadoSesion)}
              onClick={() => turno({ runtime: id, cambiar_runtime: !!runtimeElegido })}
            >
              <div className={styles.runtimeName}>{runtimeLabel(id)}</div>
              <p className={styles.runtimeField}>
                <span className={styles.runtimeFieldLabel}>Para qué sirve: </span>
                {(ficha.recomendado_para ?? []).join(" · ")}
              </p>
              <p className={styles.runtimeField}>
                <span className={styles.runtimeFieldLabel}>Necesita: </span>
                {(ficha.credenciales ?? []).join(" · ")}
              </p>
              <p className={styles.runtimeField}>
                <span className={styles.runtimeFieldLabel}>Dónde corre: </span>
                {ficha.ejecucion === "local" ? "En tu máquina" : "Integración externa"}
              </p>
              <p className={styles.runtimeField}>
                <span className={styles.runtimeFieldLabel}>Si falla: </span>
                {ficha.si_falla}
              </p>
              <p className={styles.runtimeField}>
                <span className={styles.runtimeFieldLabel}>Cómo cambiarlo: </span>
                {ficha.como_cambiar}
              </p>
              {motivo ? <p className={styles.unavailable}>{motivo}</p> : null}
            </button>
          );
        })}
      </div>

      {pregunta ? (
        <div className={styles.question}>
          <p className={styles.questionText}>{pregunta.texto}</p>
          <p className={styles.questionWhy}>{pregunta.motivo}</p>
          <input
            className={styles.input}
            value={respuesta}
            onChange={(e) => setRespuesta(e.target.value)}
            placeholder={
              pregunta.opciones.length > 0
                ? `Por ejemplo: ${pregunta.opciones.join(", ")}`
                : "Escribí tu respuesta"
            }
          />
        </div>
      ) : null}

      <div className={styles.actions}>
        {acciones.map((a) => (
          <span className={styles.actionSlot} key={a.id}>
            <button
              type="button"
              className={styles.action}
              disabled={ocupado || !a.habilitado}
              onClick={() => ejecutar(a.id)}
            >
              {ETIQUETA_ACCION[a.id] ?? a.id}
            </button>
            {!a.habilitado && a.motivo ? (
              <span className={styles.actionReason}>{a.motivo}</span>
            ) : null}
          </span>
        ))}
      </div>

      {patch ? (
        <div className={styles.diff}>
          {patch.cambios.map((c) => (
            <div
              className={c.sensible ? `${styles.diffRow} ${styles.diffSensitive}` : styles.diffRow}
              key={c.path_texto}
            >
              <strong>{c.path_texto}</strong>: {JSON.stringify(c.antes)} →{" "}
              {JSON.stringify(c.despues)} — {c.motivo}
            </div>
          ))}
          {patch.rechazos.map((r) => (
            <div className={`${styles.diffRow} ${styles.diffSensitive}`} key={r}>
              {r}
            </div>
          ))}
        </div>
      ) : null}

      {mensaje ? <div className={styles.notice}>{mensaje}</div> : null}
      {motivoInvalido ? (
        <div className={`${styles.notice} ${styles.warning}`}>{motivoInvalido}</div>
      ) : null}
      {advertencia ? (
        <div className={`${styles.notice} ${styles.warning}`}>{advertencia}</div>
      ) : null}
    </div>
  );
}
