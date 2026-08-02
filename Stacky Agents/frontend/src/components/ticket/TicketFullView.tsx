// Plan 287 F6 — la ficha del ticket a pantalla completa, la MISMA para los dos
// sistemas de tickets.
//
// v2/C3 — FORMA OBLIGATORIA: import CON LLAVES desde el BARRIL `../ui`.
// `import Dialog from "../ui/Dialog"` (lo que decia la v1) NO matchea
// UI_DIALOG_IMPORT_RE del ratchet de modales ad-hoc: la expresion exige llaves y
// una ruta terminada en `ui`. Y la allowlist no tiene lugar libre.
//
// Este archivo NUNCA escribe a mano los tres marcadores de modal que busca
// DETECT_RE (el atributo de modalidad de ARIA, el rol de dialogo y la llamada al
// portal de React): los aporta `Dialog`, que ademas trae Escape, trampa de foco,
// restauracion de foco y bloqueo de scroll.
//
// Cero estilo en linea y cero colores hex: archivo nuevo => base 0 en el ratchet
// de deuda visual, no hay margen. Toda la logica testeable vive en
// services/ticketDetailModel.ts (.ts puro), porque en este repositorio no estan
// instalados RTL ni jsdom y un componente no se puede montar en una prueba.
//
// NOTA para el proximo que edite esto: los cuatro gates de F6 son grep sobre el
// TEXTO del archivo, comentarios incluidos. Nombrar el patron prohibido en un
// comentario lo rompe igual que usarlo.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Maximize2, X, ChevronRight } from "lucide-react";

import { Dialog } from "../ui";
import { Tickets } from "../../api/endpoints";
import { formatLoadErrorMessage } from "../../utils/loadError";
import {
  construirNavegacion,
  etiquetaDeSalto,
} from "../../services/ticketDetailModel";
import type { TicketHierarchy, TicketNode } from "../../types";
import { TrackerDeepLink } from "../TrackerDeepLink";
import styles from "./TicketFullView.module.css";

export interface TicketFullViewProps {
  ticketId: number;
  /** El arbol YA cacheado por el tablero. v2/C6: tiene que ser el CRUDO
   *  (`hierarchy`), NUNCA el filtrado por "mias" (`displayHierarchy`): una ficha
   *  que oculta la mitad del arbol miente y la navegacion muere en silencio. */
  jerarquia: TicketHierarchy | undefined;
  onCerrar: () => void;
  /** Navegacion sin cerrar la ficha. */
  onCambiarFoco: (id: number) => void;
}

const CAP_COMENTARIOS = "tracker.comments.list";
const CAP_ADJUNTOS = "tracker.attachments.list";
const CAP_HISTORIAL = "tracker.updates.history";

type EstadoCapacidad = { estado: string; perdida: string } | undefined;

/** Regla 3 de F6: ningun panel queda vacio y mudo. Si el sistema de tickets
 *  declara que trae la informacion incompleta, se dice QUE se pierde. */
function AvisoDeCapacidad({ cap }: { cap: EstadoCapacidad }) {
  if (!cap) return null;
  if (cap.estado === "absent") {
    return (
      <p className={styles.avisoAusente}>
        Este sistema de tickets no ofrece este dato.
      </p>
    );
  }
  if (cap.estado === "partial" && cap.perdida.trim()) {
    return <p className={styles.aviso}>Viene incompleto: {cap.perdida}</p>;
  }
  return null;
}

function ListaDeSaltos({
  nodos,
  onCambiarFoco,
}: {
  nodos: TicketNode[];
  onCambiarFoco: (id: number) => void;
}) {
  if (nodos.length === 0) return <p className={styles.vacio}>Ninguno.</p>;
  return (
    <div className={styles.saltos}>
      {nodos.map((n) => (
        <button
          key={n.id}
          type="button"
          className={styles.salto}
          onClick={() => onCambiarFoco(n.id)}
        >
          {etiquetaDeSalto(n)}
        </button>
      ))}
    </div>
  );
}

export default function TicketFullView({
  ticketId,
  jerarquia,
  onCerrar,
  onCambiarFoco,
}: TicketFullViewProps) {
  // F4, puro: sin una sola llamada nueva al servidor.
  const nav = construirNavegacion(jerarquia, ticketId);

  // Regla 5: el historial se consulta SOLO cuando el operador abre el panel.
  // Sin esto, abrir una ficha dispara una consulta que el operador no pidio.
  const [panelHistorialAbierto, setPanelHistorialAbierto] = useState(false);

  const detalleQ = useQuery({
    queryKey: ["ticket-detalle", ticketId],
    queryFn: () => Tickets.byId(ticketId),
    staleTime: 30_000,
  });
  const comentariosQ = useQuery({
    queryKey: ["ticket-comentarios", ticketId],
    queryFn: () => Tickets.comments(ticketId),
    staleTime: 60_000,
  });
  const adjuntosQ = useQuery({
    queryKey: ["ticket-adjuntos", ticketId],
    queryFn: () => Tickets.attachments(ticketId),
    staleTime: 60_000,
  });
  const historialQ = useQuery({
    queryKey: ["ticket-historial", ticketId],
    queryFn: () => Tickets.historial(ticketId),
    enabled: panelHistorialAbierto,
    staleTime: 60_000,
  });
  const capacidadesQ = useQuery({
    queryKey: ["tracker-capacidades"],
    queryFn: () => Tickets.capacidades(),
    staleTime: 5 * 60_000,
  });

  const caps = capacidadesQ.data?.capacidades;
  const detalle = detalleQ.data;
  const foco = nav.foco;
  const identidad = etiquetaDeSalto({
    ado_id: detalle?.ado_id ?? foco?.ado_id ?? ticketId,
    work_item_type: detalle?.work_item_type ?? foco?.work_item_type,
    ado_state: detalle?.ado_state ?? foco?.ado_state,
  });

  return (
    <Dialog
      open
      bare
      panelClassName={styles.ficha}
      onClose={onCerrar}
      ariaLabel={`Ficha del ticket ${ticketId}`}
    >
      <header className={styles.cabecera}>
        <span className={styles.identidad}>
          <Maximize2 size={14} aria-hidden="true" />
          {identidad}
        </span>
        <h2 className={styles.titulo}>
          {detalle?.title ?? foco?.title ?? "Cargando la ficha…"}
        </h2>
        <div className={styles.accionesCabecera}>
          {/* Provider-agnostico: el servidor da la URL, la interfaz NO la compone.
              Si viene null (deep links apagados o proyecto sin soporte) el propio
              componente cae a un <span> sin enlace. */}
          <TrackerDeepLink
            url={detalle?.item_url ?? detalle?.ado_url ?? foco?.item_url ?? foco?.ado_url}
            label="Abrir en el sistema de tickets"
            className={styles.botonPanel}
          />
          <button
            type="button"
            className={styles.botonPanel}
            onClick={onCerrar}
            aria-label="Cerrar la ficha"
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className={styles.cuerpo}>
        {/* ── Columna 1 — jerarquia navegable ─────────────────────────────── */}
        <section className={styles.columna} aria-label="Jerarquia">
          {nav.focoFueraDelArbol && (
            <p className={styles.avisoAusente}>
              Este ticket no esta en el arbol cargado del proyecto activo.
            </p>
          )}

          <div className={styles.panel}>
            <h3 className={styles.panelTitulo}>
              Ancestros <ChevronRight size={12} aria-hidden="true" />
            </h3>
            <ListaDeSaltos nodos={nav.cadenaAncestros} onCambiarFoco={onCambiarFoco} />
            {/* Regla 4: el huerfano DICE por que quedo suelto (cierra K6). */}
            {nav.motivoHuerfano != null && (
              <p className={styles.motivoHuerfano}>{nav.motivoHuerfano}</p>
            )}
          </div>

          <div className={styles.panel}>
            <h3 className={styles.panelTitulo}>Hijos ({nav.hijos.length})</h3>
            <ListaDeSaltos nodos={nav.hijos} onCambiarFoco={onCambiarFoco} />
          </div>

          <div className={styles.panel}>
            <h3 className={styles.panelTitulo}>Hermanos ({nav.hermanos.length})</h3>
            <ListaDeSaltos nodos={nav.hermanos} onCambiarFoco={onCambiarFoco} />
          </div>
        </section>

        {/* ── Columna 2 — contenido ────────────────────────────────────────── */}
        <section className={styles.columna} aria-label="Contenido">
          <div className={styles.panel}>
            <h3 className={styles.panelTitulo}>Descripcion</h3>
            {detalleQ.isError ? (
              <p className={styles.error}>{formatLoadErrorMessage(detalleQ.error)}</p>
            ) : (
              <div className={styles.panelCuerpo}>
                {detalle?.description?.trim() || (
                  <span className={styles.vacio}>Sin descripcion.</span>
                )}
              </div>
            )}
          </div>

          <div className={styles.panel}>
            <h3 className={styles.panelTitulo}>
              Comentarios ({comentariosQ.data?.comments?.length ?? 0})
            </h3>
            <AvisoDeCapacidad cap={caps?.[CAP_COMENTARIOS]} />
            {comentariosQ.isError ? (
              <p className={styles.error}>{formatLoadErrorMessage(comentariosQ.error)}</p>
            ) : (comentariosQ.data?.comments?.length ?? 0) === 0 ? (
              <p className={styles.vacio}>Sin comentarios.</p>
            ) : (
              <div className={styles.panelCuerpo}>
                {comentariosQ.data?.comments?.map((c, i) => (
                  <p key={i}>{c.text}</p>
                ))}
              </div>
            )}
          </div>

          <div className={styles.panel}>
            <h3 className={styles.panelTitulo}>
              Historial de cambios ({historialQ.data?.historial?.length ?? 0})
              <button
                type="button"
                className={styles.botonPanel}
                aria-expanded={panelHistorialAbierto}
                onClick={() => setPanelHistorialAbierto((v) => !v)}
              >
                {panelHistorialAbierto ? "Ocultar" : "Ver"}
              </button>
            </h3>
            {panelHistorialAbierto && (
              <>
                <AvisoDeCapacidad
                  cap={historialQ.data?.capacidad ?? caps?.[CAP_HISTORIAL]}
                />
                {historialQ.isError ? (
                  <p className={styles.error}>{formatLoadErrorMessage(historialQ.error)}</p>
                ) : (historialQ.data?.historial?.length ?? 0) === 0 ? (
                  <p className={styles.vacio}>Sin cambios registrados.</p>
                ) : (
                  <table className={styles.tablaHistorial}>
                    <thead>
                      <tr>
                        <th scope="col">Cuando</th>
                        <th scope="col">Quien</th>
                        <th scope="col">Que</th>
                        <th scope="col">De</th>
                        <th scope="col">A</th>
                      </tr>
                    </thead>
                    <tbody>
                      {historialQ.data?.historial?.map((f, i) => (
                        <tr key={i}>
                          <td>{f.fecha ?? "—"}</td>
                          <td>{f.autor ?? "—"}</td>
                          <td>{f.campo ?? "—"}</td>
                          <td>{f.de ?? "—"}</td>
                          <td>{f.a ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </div>
        </section>

        {/* ── Columna 3 — ficha y acciones ─────────────────────────────────── */}
        <section className={styles.columna} aria-label="Ficha y acciones">
          <div className={styles.panel}>
            <h3 className={styles.panelTitulo}>Ficha</h3>
            <dl className={styles.datos}>
              <dt className={styles.datoClave}>Asignado a</dt>
              <dd className={styles.datoValor}>
                {detalle?.assigned_to_ado ?? detalle?.assignee ?? "sin asignar"}
              </dd>
              <dt className={styles.datoClave}>Prioridad</dt>
              <dd className={styles.datoValor}>{detalle?.priority ?? "—"}</dd>
              <dt className={styles.datoClave}>Estado</dt>
              <dd className={styles.datoValor}>{detalle?.ado_state ?? "—"}</dd>
              <dt className={styles.datoClave}>Ultima sincronizacion</dt>
              <dd className={styles.datoValor}>{detalle?.last_synced_at ?? "—"}</dd>
            </dl>
          </div>

          <div className={styles.panel}>
            <h3 className={styles.panelTitulo}>
              Adjuntos ({adjuntosQ.data?.attachments?.length ?? 0})
            </h3>
            <AvisoDeCapacidad cap={caps?.[CAP_ADJUNTOS]} />
            {adjuntosQ.isError ? (
              <p className={styles.error}>{formatLoadErrorMessage(adjuntosQ.error)}</p>
            ) : (adjuntosQ.data?.attachments?.length ?? 0) === 0 ? (
              <p className={styles.vacio}>Sin adjuntos.</p>
            ) : (
              <div className={styles.saltos}>
                {adjuntosQ.data?.attachments?.map((a, i) => (
                  <span key={i} className={styles.salto}>{a.name}</span>
                ))}
              </div>
            )}
          </div>

          <div className={styles.panel}>
            <h3 className={styles.panelTitulo}>
              Ejecuciones ({detalle?.executions?.length ?? 0})
            </h3>
            {(detalle?.executions?.length ?? 0) === 0 ? (
              <p className={styles.vacio}>Sin ejecuciones.</p>
            ) : (
              <div className={styles.saltos}>
                {detalle?.executions?.map((e) => (
                  <span key={e.id} className={styles.salto}>
                    {e.id} · {e.agent_type} · {e.status}
                  </span>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </Dialog>
  );
}
