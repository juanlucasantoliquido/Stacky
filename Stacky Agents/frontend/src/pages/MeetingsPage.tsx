/**
 * Plan 283 F9 — Pantalla de Reuniones. UNA sola pantalla para todo el ciclo
 * (K3): cargar lo que se dijo, ver la minuta, y llevar un compromiso a una
 * tarea real. Ninguna accion manda al operador a otra seccion.
 *
 * Toda la LOGICA vive en `services/meetingsModel.ts` y esta probada ahi: RTL y
 * jsdom NO estan instalados, asi que un `.test.tsx` reportaria "no tests" con
 * exit 0. Este archivo es cascara de pintura y se verifica con smoke manual.
 *
 * Reglas de la casa que respeta: cero estilos en linea y cero color
 * hexadecimal (todo por `MeetingsPage.module.css` con tokens del tema), cero
 * dialogos nativos del navegador, cero controles de formulario crudos (van las
 * primitivas de `components/ui`), y cero formateo nativo de fechas (va
 * `services/format`).
 *
 * OJO: este comentario NO puede citar textualmente el patron que busca
 * `uiDebtRatchet` — el ratchet escanea el archivo entero, comentarios incluidos,
 * y la primera version de este encabezado se auto-delato.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Field,
  SectionHeader,
  Skeleton,
  StatusChip,
  Textarea,
  type StatusTone,
} from "../components/ui";
import { formatDate, formatDateTime } from "../services/format";
import {
  accionesDisponibles,
  agruparPorDia,
  etiquetaEstadoMinuta,
  puedePublicar,
  resumenCalendario,
  type MeetingRow,
} from "../services/meetingsModel";
import {
  Meetings,
  MeetingsPublish,
  type ActionItemDto,
  type CalendarioDto,
  type MeetingDetalleDto,
  type MeetingDto,
} from "../api/meetings";
import styles from "./MeetingsPage.module.css";

function aRow(m: MeetingDto): MeetingRow {
  return {
    id: m.id,
    subject: m.subject,
    startedAt: m.started_at,
    minutesState: m.minutes_state,
    pendientes: m.action_items_count,
  };
}

function tonoDeAtribucion(a: ActionItemDto["atribucion"]): StatusTone {
  if (a === "confirmada") return "success";
  if (a === "sin_hablante") return "warning";
  return "neutral";
}

function textoDeAtribucion(a: ActionItemDto["atribucion"]): string {
  if (a === "confirmada") return "Responsable verificado";
  if (a === "sin_hablante") return "Responsable sin verificar";
  return "Sin responsable";
}

export default function MeetingsPage() {
  const [cargando, setCargando] = useState(true);
  const [reuniones, setReuniones] = useState<MeetingDto[]>([]);
  const [seleccionada, setSeleccionada] = useState<MeetingDetalleDto | null>(null);
  const [calendario, setCalendario] = useState<CalendarioDto | null>(null);
  const [publicarOn, setPublicarOn] = useState(false);
  const [texto, setTexto] = useState("");
  const [mensaje, setMensaje] = useState("");
  const [trabajando, setTrabajando] = useState(false);

  const recargar = useCallback(async () => {
    setCargando(true);
    try {
      const [lista, salud] = await Promise.all([Meetings.list(), Meetings.health()]);
      setReuniones(lista.data?.meetings ?? []);
      setPublicarOn(Boolean(salud.data?.publish_enabled));
    } catch {
      setMensaje("No se pudo hablar con Stacky. Revisa que este corriendo.");
    } finally {
      setCargando(false);
    }
  }, []);

  const traerCalendario = useCallback(async () => {
    try {
      const res = await Meetings.calendar();
      setCalendario(res.data ?? null);
    } catch {
      setCalendario({ estado: "error", reuniones: [], detalle: "No se pudo consultar." });
    }
  }, []);

  useEffect(() => {
    void recargar();
    void traerCalendario();
  }, [recargar, traerCalendario]);

  const abrir = useCallback(async (id: number) => {
    setMensaje("");
    try {
      const res = await Meetings.get(id);
      setSeleccionada(res.data?.meeting ?? null);
      setTexto("");
    } catch {
      setMensaje("No se pudo abrir la reunion.");
    }
  }, []);

  const crear = useCallback(async () => {
    setTrabajando(true);
    try {
      const res = await Meetings.create({ subject: "Reunion nueva" });
      await recargar();
      if (res.data?.id) await abrir(res.data.id);
    } finally {
      setTrabajando(false);
    }
  }, [abrir, recargar]);

  const guardarTexto = useCallback(async () => {
    if (!seleccionada || !texto.trim()) return;
    setTrabajando(true);
    setMensaje("");
    try {
      const res = await Meetings.putTranscript(seleccionada.id, { content: texto });
      if (res.data?.meeting) setSeleccionada(res.data.meeting);
      if (!res.data?.ok) setMensaje(res.data?.detalle || "No se pudo generar la minuta.");
      await abrir(seleccionada.id);
      await recargar();
    } catch {
      setMensaje("No se pudo guardar el texto de la reunion.");
    } finally {
      setTrabajando(false);
    }
  }, [abrir, recargar, seleccionada, texto]);

  const regenerar = useCallback(async () => {
    if (!seleccionada) return;
    setTrabajando(true);
    try {
      const res = await Meetings.retry(seleccionada.id);
      if (!res.data?.ok) setMensaje(res.data?.detalle || "No se pudo regenerar la minuta.");
      await abrir(seleccionada.id);
      await recargar();
    } finally {
      setTrabajando(false);
    }
  }, [abrir, recargar, seleccionada]);

  /**
   * Dos pasos, siempre: el borrador NO escribe nada y devuelve una confirmacion
   * de un solo uso; recien el segundo llamado crea la tarea de verdad. Es el
   * mismo interlock que usa el resto de Stacky para lo irreversible.
   */
  const publicar = useCallback(async (item: ActionItemDto) => {
    setTrabajando(true);
    setMensaje("");
    try {
      const borrador = await MeetingsPublish.draft(item.id);
      const token = borrador.data?.confirm_token;
      if (!token) {
        setMensaje(borrador.errorBody?.message || "No se pudo preparar la publicacion.");
        return;
      }
      const hecho = await MeetingsPublish.confirm(item.id, token);
      if (hecho.data?.ok) {
        setMensaje(`Tarea creada: ${hecho.data.external_id}`);
        if (seleccionada) await abrir(seleccionada.id);
      } else {
        setMensaje(hecho.errorBody?.message || "No se pudo crear la tarea.");
      }
    } catch {
      setMensaje("No se pudo crear la tarea.");
    } finally {
      setTrabajando(false);
    }
  }, [abrir, seleccionada]);

  const grupos = agruparPorDia(reuniones.map(aRow));
  const resumen = calendario ? resumenCalendario(calendario.estado) : null;
  const acciones = seleccionada
    ? accionesDisponibles(aRow(seleccionada), { publishOn: publicarOn })
    : [];

  return (
    <div className={styles.page}>
      <SectionHeader
        title="Reuniones"
        subtitle="De lo que se dijo en la reunion a la minuta y los compromisos, en un solo lugar."
        actions={
          <div className={styles.acciones}>
            <Button onClick={() => void traerCalendario()} disabled={trabajando}>
              Actualizar el calendario
            </Button>
            <Button variant="primary" onClick={() => void crear()} disabled={trabajando}>
              Cargar una reunion
            </Button>
          </div>
        }
      />

      {resumen && (
        <div className={resumen.accionable ? `${styles.aviso} ${styles.avisoAccionable}` : styles.aviso}>
          {resumen.texto}
        </div>
      )}
      {mensaje && <div className={styles.aviso}>{mensaje}</div>}

      <div className={styles.columnas}>
        <Card>
          <div className={styles.bloque}>
            {cargando && <Skeleton lines={4} />}
            {!cargando && grupos.length === 0 && (
              <p className={styles.vacio}>
                Todavia no hay reuniones. Carga una y pega lo que se dijo.
              </p>
            )}
            {!cargando &&
              grupos.map((g) => (
                <div className={styles.grupoDia} key={g.dia}>
                  <div className={styles.tituloDia}>{g.dia}</div>
                  {g.rows.map((r) => (
                    <button
                      type="button"
                      key={r.id}
                      className={
                        seleccionada?.id === r.id ? `${styles.fila} ${styles.filaActiva}` : styles.fila
                      }
                      onClick={() => void abrir(r.id)}
                    >
                      <span className={styles.filaTexto}>
                        <span className={styles.filaTitulo}>{r.subject}</span>
                        <span className={styles.filaMeta}>
                          {r.startedAt ? formatDateTime(r.startedAt) : "Sin fecha"} ·{" "}
                          {etiquetaEstadoMinuta(r.minutesState)} · {r.pendientes} compromisos
                        </span>
                      </span>
                      <StatusChip tone={r.minutesState === "done" ? "success" : "neutral"}>
                        {etiquetaEstadoMinuta(r.minutesState)}
                      </StatusChip>
                    </button>
                  ))}
                </div>
              ))}
          </div>
        </Card>

        <Card>
          <div className={styles.bloque}>
            {!seleccionada && (
              <p className={styles.vacio}>Elegi una reunion de la lista para ver su detalle.</p>
            )}

            {seleccionada && (
              <>
                <SectionHeader
                  title={seleccionada.subject}
                  subtitle={
                    seleccionada.started_at
                      ? formatDate(seleccionada.started_at)
                      : "Sin fecha registrada"
                  }
                />

                <div className={styles.acciones}>
                  {acciones.map((a) => (
                    <Button
                      key={a.id}
                      disabled={!a.habilitada || trabajando}
                      onClick={() => {
                        if (a.id === "regenerar") void regenerar();
                        if (a.id === "actualizar") void traerCalendario();
                      }}
                    >
                      {a.label}
                    </Button>
                  ))}
                </div>

                <Field
                  label="Lo que se dijo en la reunion"
                  help="Pega el archivo de subtitulos que deja Teams, o el texto tal cual."
                >
                  {(ctl) => (
                    <Textarea
                      {...ctl}
                      className={styles.textoLargo}
                      rows={8}
                      value={texto}
                      onChange={(e) => setTexto(e.target.value)}
                    />
                  )}
                </Field>
                <div className={styles.acciones}>
                  <Button
                    variant="primary"
                    disabled={trabajando || !texto.trim()}
                    onClick={() => void guardarTexto()}
                  >
                    Guardar y generar la minuta
                  </Button>
                </div>

                {seleccionada.minutes?.aviso_truncado && (
                  <div className={styles.aviso}>{seleccionada.minutes.aviso_truncado}</div>
                )}
                {seleccionada.minutes && (
                  <>
                    <p>{seleccionada.minutes.resumen}</p>
                    {seleccionada.minutes.descartados_sin_cita > 0 && (
                      <div className={styles.aviso}>
                        Se descartaron {seleccionada.minutes.descartados_sin_cita} puntos porque no
                        se pudo encontrar la frase textual que los respalde.
                      </div>
                    )}
                  </>
                )}

                {seleccionada.action_items.map((item) => (
                  <div
                    key={item.id}
                    className={
                      item.atribucion === "sin_hablante"
                        ? `${styles.pendiente} ${styles.pendienteDudoso}`
                        : styles.pendiente
                    }
                  >
                    <strong>{item.titulo}</strong>
                    <div className={styles.filaMeta}>
                      {item.responsable ? item.responsable : "Sin responsable"}
                      {item.fecha_compromiso ? ` · ${formatDate(item.fecha_compromiso)}` : ""}
                    </div>
                    <StatusChip tone={tonoDeAtribucion(item.atribucion)}>
                      {textoDeAtribucion(item.atribucion)}
                    </StatusChip>
                    <blockquote className={styles.cita}>{item.cita}</blockquote>
                    <div className={styles.acciones}>
                      <Button
                        disabled={!puedePublicar(item, publicarOn) || trabajando}
                        onClick={() => void publicar(item)}
                      >
                        {item.estado === "publicado"
                          ? `Ya publicado (${item.external_id ?? ""})`
                          : "Crear tarea desde este compromiso"}
                      </Button>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
