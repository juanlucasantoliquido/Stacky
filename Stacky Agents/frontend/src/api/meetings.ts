/**
 * Plan 283 F9 — Cliente HTTP del modulo de Reuniones.
 *
 * DESVIO DECLARADO respecto del plan: el plan pedia un namespace `Meetings`
 * dentro de `api/endpoints.ts`. Ese archivo tiene cambios SIN COMMITEAR de otra
 * sesion que corre en este mismo arbol, asi que se aplica el mismo criterio que
 * el plan aplica a `api/tickets.py` (D6): archivo propio, cero conflicto con
 * trabajo real. El contrato y los moldes son identicos.
 *
 * REGLA DURA DE LA CASA: `api.*` LANZA en cualquier respuesta non-2xx. En estas
 * rutas un 404 (capacidad apagada) y un 409 (falta confirmar) son respuestas
 * NORMALES que hay que PINTAR, no excepciones. Por eso TODO va por
 * `rawGet`/`rawPost`, que devuelven `RawResponse<T>` y no lanzan en 4xx/5xx.
 * Ojo: `raw*` SI re-lanza errores de red y de aborto, asi que el consumidor
 * necesita try/catch ADEMAS de mirar `res.ok`.
 */
import { rawGet, rawPost, type RawResponse } from "./client";

export interface MeetingDto {
  id: number;
  source: string;
  external_id: string | null;
  stacky_project_name: string;
  subject: string;
  organizer: string | null;
  started_at: string | null;
  ended_at: string | null;
  join_url: string | null;
  transcript_format: string | null;
  minutes_state: "pending" | "done" | "failed" | "blocked";
  created_at: string | null;
  updated_at: string | null;
  action_items_count: number;
}

export interface ActionItemDto {
  id: number;
  meeting_id: number;
  titulo: string;
  responsable: string | null;
  fecha_compromiso: string | null;
  cita: string;
  estado: string;
  atribucion: "confirmada" | "sin_hablante" | "sin_responsable";
  tracker_type: string | null;
  external_id: string | null;
  created_at: string | null;
}

export interface MinutasDto {
  resumen: string;
  decisiones: { texto: string; cita: string }[];
  pendientes: {
    titulo: string;
    responsable: string | null;
    fecha_compromiso: string | null;
    cita: string;
    atribucion: string;
  }[];
  riesgos: { texto: string; cita: string }[];
  descartados_sin_cita: number;
  sin_hablante: number;
  aviso_truncado: string | null;
}

export interface MeetingDetalleDto extends MeetingDto {
  minutes: MinutasDto | null;
  transcript_chars: number;
  action_items: ActionItemDto[];
}

export interface CalendarioDto {
  estado: "ok" | "sin_credenciales" | "apagado" | "error";
  reuniones: {
    source: string;
    external_id: string | null;
    subject: string;
    organizer: string | null;
    started_at: string | null;
    ended_at: string | null;
    join_url: string | null;
  }[];
  detalle: string;
}

export interface ProbeDto {
  config: boolean;
  auth: boolean;
  calendario: boolean;
  detalle: string;
}

export interface BorradorDto {
  item_id: number;
  meeting_id: number;
  project: string;
  item_type: string;
  title: string;
  description_html: string;
  labels: string[];
  assignee: string | null;
  atribucion: string;
  cita: string;
}

const qs = (project?: string | null) =>
  project ? `?project=${encodeURIComponent(project)}` : "";

export const Meetings = {
  /** SIEMPRE 200, incluso con la capacidad apagada: alimenta el gate de nav. */
  health: () =>
    rawGet<{ ok: boolean; flag_enabled: boolean; graph_enabled: boolean; publish_enabled: boolean }>(
      "/api/meetings/health",
    ),

  list: (project?: string | null) =>
    rawGet<{ ok: boolean; project: string; meetings: MeetingDto[] }>(`/api/meetings${qs(project)}`),

  get: (id: number, project?: string | null) =>
    rawGet<{ ok: boolean; meeting: MeetingDetalleDto }>(`/api/meetings/${id}${qs(project)}`),

  create: (body: { subject: string; started_at?: string | null; organizer?: string | null },
           project?: string | null) =>
    rawPost<{ ok: boolean; id: number }>(`/api/meetings${qs(project)}`, body),

  /** Guarda el texto Y genera la minuta en el mismo pedido. */
  putTranscript: (id: number, body: { content: string; format?: string | null },
                  project?: string | null) =>
    rawPost<{ ok: boolean; estado: string; detalle: string; meeting: MeetingDetalleDto }>(
      `/api/meetings/${id}/transcript${qs(project)}`, body,
    ),

  retry: (id: number, project?: string | null) =>
    rawPost<{ ok: boolean; estado: string; detalle: string; meeting: MeetingDetalleDto }>(
      `/api/meetings/${id}/minutes/retry${qs(project)}`, {},
    ),

  /** NUNCA 500: el `estado` de la degradacion viaja en el cuerpo. */
  calendar: (project?: string | null, dias = 14) =>
    rawGet<CalendarioDto>(
      `/api/meetings/calendar${qs(project)}${project ? "&" : "?"}dias=${dias}`,
    ),

  probe: (project?: string | null) => rawGet<ProbeDto>(`/api/meetings/graph/probe${qs(project)}`),

  deviceLogin: (project?: string | null) =>
    rawPost<{ ok: boolean; user_code: string; verification_uri: string; interval: number }>(
      `/api/meetings/graph/device-login${qs(project)}`, {},
    ),

  devicePoll: (project?: string | null) =>
    rawPost<{ ok: boolean; estado: string; detalle: string }>(
      `/api/meetings/graph/device-poll${qs(project)}`, {},
    ),

  graphTranscript: (externalId: string, project?: string | null) =>
    rawGet<{ ok: boolean; content: string; format: string }>(
      `/api/meetings/graph/transcript/${encodeURIComponent(externalId)}${qs(project)}`,
    ),
};

export const MeetingsPublish = {
  /** No escribe nada: devuelve el borrador y una confirmacion de un solo uso. */
  draft: (itemId: number, project?: string | null) =>
    rawPost<{ ok: boolean; draft: BorradorDto; confirm_token: string; expires_in: number }>(
      `/api/meetings-publish/${itemId}/draft${qs(project)}`, {},
    ),

  confirm: (itemId: number, confirmToken: string, project?: string | null) =>
    rawPost<{ ok: boolean; item_id: number; external_id: string; url: string }>(
      `/api/meetings-publish/${itemId}/confirm${qs(project)}`, { confirm_token: confirmToken },
    ),
};

export type { RawResponse };
