/**
 * WorkbenchPage.tsx — Plan 293 F13. El tablero de trabajo.
 *
 * Este componente SOLO PINTA. Toda la lógica testeable vive en
 * `services/publishWizardModel.ts` y `services/workbenchErrors.ts`, porque
 * RTL/jsdom no están instalados: un `.test.tsx` con RTL reporta "no tests" y
 * sale con exit 0 — un falso verde perfecto.
 *
 * Se usa `rawGet`/`rawPost` y NO el wrapper `api.*`: ese lanza en non-2xx y acá
 * el cuerpo del error ES la información (trae el código que se traduce).
 */
import { useCallback, useEffect, useState } from "react";
import { rawGet, rawPost } from "../api/client";
import { traducir } from "../services/workbenchErrors";
import {
  ESTADO_INICIAL, PASOS, agruparParaPintar, alternar, avisosParaElPrimerPaso,
  bloqueosParaElPrimerPaso, motivoParaNoAvanzar, pasoAnterior, pasoSiguiente,
  puedeAvanzar, resumenSeleccion, textoContador,
  type EstadoAsistente, type EstadoTablero,
} from "../services/publishWizardModel";
import styles from "./WorkbenchPage.module.css";

const TITULO_PASO: Record<string, string> = {
  revisar: "1. Mirá qué cambió",
  elegir: "2. Elegí qué guardar",
  describir: "3. Contá qué hiciste",
  confirmar: "4. Confirmá",
};

interface Flags { lectura: boolean; escritura: boolean; envio: boolean }

export default function WorkbenchPage() {
  const [tablero, setTablero] = useState<EstadoTablero | null>(null);
  const [flags, setFlags] = useState<Flags>({ lectura: true, escritura: false, envio: false });
  const [rama, setRama] = useState<string>("");
  const [estado, setEstado] = useState<EstadoAsistente>(ESTADO_INICIAL);
  const [diff, setDiff] = useState<{ path: string; texto: string } | null>(null);
  const [resultado, setResultado] = useState<{ ok: boolean; codigo?: string; detalle?: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [historial, setHistorial] = useState<Array<Record<string, string>>>([]);

  const cargar = useCallback(async () => {
    const r = await rawGet<Record<string, unknown>>("/api/workbench/overview");
    const d = r.data as unknown as (EstadoTablero & { repo?: { branch?: string }; flags?: Flags }) | null;
    if (d) {
      setTablero(d);
      setRama(d.repo?.branch ?? "");
      if (d.flags) setFlags(d.flags);
    }
    const h = await rawGet<{ commits?: Array<Record<string, string>> }>("/api/workbench/historial?n=10");
    setHistorial(h.data?.commits ?? []);
  }, []);

  useEffect(() => { void cargar(); }, [cargar]);

  const verDiff = async (path: string) => {
    const r = await rawGet<{ diff?: string; reason?: string }>(
      `/api/workbench/diff?path=${encodeURIComponent(path)}`,
    );
    setDiff({ path, texto: r.data?.diff || r.data?.reason || "Sin diferencias para mostrar." });
  };

  const accionar = async (ruta: string, cuerpo: Record<string, unknown>) => {
    setOcupado(true);
    setResultado(null);
    const r = await rawPost<{ ok?: boolean; codigo?: string; sha?: string }>(ruta, { ...cuerpo, confirm: true });
    const cuerpoRes = r.data ?? {};
    setResultado(
      cuerpoRes.ok
        ? { ok: true, detalle: cuerpoRes.sha ? `Guardado (${String(cuerpoRes.sha).slice(0, 7)})` : "Listo." }
        : { ok: false, codigo: cuerpoRes.codigo ?? r.errorBody?.error ?? "desconocido" },
    );
    setOcupado(false);
    await cargar();
    if (cuerpoRes.ok) setEstado((e) => ({ ...ESTADO_INICIAL, paso: e.paso === "confirmar" ? "revisar" : e.paso }));
  };

  if (!tablero) return <div className={styles.vacio}>Cargando tu carpeta de trabajo…</div>;

  if (!tablero.available) {
    const t = traducir("repo_no_disponible");
    return (
      <div className={styles.pagina}>
        <div className={styles.bloqueo}>
          <h3>{t.titulo}</h3>
          <p>{t.queSignifica}</p>
          <p className={styles.queHacer}>{t.queHacer}</p>
        </div>
      </div>
    );
  }

  const resumen = resumenSeleccion(estado.seleccion, tablero.archivos);
  const grupos = agruparParaPintar(tablero.archivos);
  const bloqueos = bloqueosParaElPrimerPaso(tablero);
  const avisos = avisosParaElPrimerPaso(tablero);
  const motivo = motivoParaNoAvanzar(estado, tablero);

  return (
    <div className={styles.pagina}>
      <header className={styles.cabecera}>
        <div>
          <h2 className={styles.titulo}>Publicar mi trabajo</h2>
          <p className={styles.subtitulo}>
            Estás trabajando en <strong>{rama || "una versión sin nombre"}</strong>.{" "}
            {resumen.total === 0
              ? "No hay cambios sin guardar."
              : `Tenés ${resumen.total} archivo${resumen.total === 1 ? "" : "s"} con cambios.`}
          </p>
        </div>
        <button className={styles.secundario} onClick={() => void cargar()} disabled={ocupado}>
          Actualizar
        </button>
      </header>

      {/* Los problemas se muestran EN EL PASO 1, no al final. */}
      {bloqueos.map((c) => {
        const t = traducir(c);
        return (
          <div key={c} className={styles.bloqueo}>
            <strong>{t.titulo}</strong>
            <p>{t.queSignifica}</p>
            <p className={styles.queHacer}>{t.queHacer}</p>
          </div>
        );
      })}
      {avisos.map((c) => {
        const t = traducir(c);
        return (
          <div key={c} className={styles.aviso}>
            <strong>{t.titulo}</strong> <span>{t.queSignifica}</span>
          </div>
        );
      })}

      <ol className={styles.pasos}>
        {PASOS.map((p) => (
          <li key={p} className={p === estado.paso ? styles.pasoActivo : styles.paso}>
            {TITULO_PASO[p]}
          </li>
        ))}
      </ol>

      <div className={styles.columnas}>
        <section className={styles.panel}>
          <h3 className={styles.panelTitulo}>Tus archivos</h3>
          {grupos.length === 0 && <p className={styles.vacio}>No hay cambios para guardar.</p>}
          {grupos.map((g) => (
            <div key={g.grupo} className={styles.grupo}>
              <h4 className={g.grupo === "conflictos" ? styles.grupoUrgente : styles.grupoTitulo}>
                {g.rotulo} ({g.archivos.length})
              </h4>
              {g.archivos.map((a) => (
                <div key={a.path} className={styles.fila}>
                  <label className={styles.etiqueta}>
                    <input
                      type="checkbox"
                      checked={estado.seleccion.includes(a.path)}
                      onChange={() => setEstado((e) => ({ ...e, seleccion: alternar(e.seleccion, a.path) }))}
                      disabled={g.grupo === "conflictos"}
                    />
                    <span className={styles.ruta}>{a.path}</span>
                  </label>
                  <button className={styles.enlace} onClick={() => void verDiff(a.path)}>
                    Ver qué cambió
                  </button>
                </div>
              ))}
            </div>
          ))}
          <p className={styles.contador}>{textoContador(resumen)}</p>
          {resumen.noElegidos > 0 && (
            <div className={styles.aviso}>
              <strong>No se van a incluir ({resumen.noElegidos})</strong>
              <ul className={styles.listaFuera}>
                {resumen.pathsNoElegidos.map((p) => <li key={p}>{p}</li>)}
              </ul>
              <span>Quedan como están. No se tocan.</span>
            </div>
          )}
        </section>

        <section className={styles.panel}>
          {diff ? (
            <>
              <h3 className={styles.panelTitulo}>Diferencias de {diff.path}</h3>
              <pre className={styles.diff}>{diff.texto}</pre>
            </>
          ) : (
            <>
              <h3 className={styles.panelTitulo}>Contá qué hiciste</h3>
              <textarea
                className={styles.texto}
                rows={4}
                placeholder="Por ejemplo: arreglé el cálculo de intereses en la pantalla de cobranzas"
                value={estado.mensaje}
                onChange={(e) => setEstado((s) => ({ ...s, mensaje: e.target.value }))}
              />
              <h4 className={styles.grupoTitulo}>Qué probaste</h4>
              <textarea
                className={styles.texto}
                rows={3}
                placeholder="Por ejemplo: abrí la pantalla y verifiqué que el total ahora da bien"
                value={estado.pruebas}
                onChange={(e) => setEstado((s) => ({ ...s, pruebas: e.target.value }))}
              />
            </>
          )}
        </section>
      </div>

      <footer className={styles.acciones}>
        <button
          className={styles.secundario}
          onClick={() => setEstado((e) => ({ ...e, paso: pasoAnterior(e.paso) }))}
          disabled={estado.paso === "revisar" || ocupado}
        >
          Volver
        </button>
        <button
          className={styles.secundario}
          onClick={() => setEstado((e) => ({ ...e, paso: pasoSiguiente(e.paso) }))}
          disabled={!puedeAvanzar(estado, tablero) || estado.paso === "confirmar" || ocupado}
          title={motivo ? traducir(motivo).queHacer : ""}
        >
          Siguiente
        </button>

        <span className={styles.separador} />

        <button
          className={styles.primario}
          disabled={!flags.escritura || estado.seleccion.length === 0 || ocupado || estado.mensaje.trim().length < 5}
          title={!flags.escritura ? traducir("escritura_apagada").queHacer : ""}
          onClick={() => void accionar("/api/workbench/confirmar", {
            rutas: estado.seleccion,
            mensaje: `${estado.mensaje}${estado.pruebas ? `\n\nQué probé:\n${estado.pruebas}` : ""}`,
          })}
        >
          Guardar los {estado.seleccion.length} elegidos
        </button>
        <button
          className={styles.secundario}
          disabled={!flags.escritura || ocupado}
          title={!flags.escritura ? traducir("escritura_apagada").queHacer : ""}
          onClick={() => void accionar("/api/workbench/traer", {})}
        >
          Traer cambios
        </button>
        <button
          className={styles.secundario}
          disabled={!flags.envio || ocupado}
          title={!flags.envio ? traducir("push_apagado").queHacer : ""}
          onClick={() => void accionar("/api/workbench/enviar", { rama })}
        >
          Enviar al servidor
        </button>
      </footer>

      {resultado && !resultado.ok && (() => {
        const t = traducir(resultado.codigo);
        return (
          <div className={styles.bloqueo}>
            <strong>{t.titulo}</strong>
            <p>{t.queSignifica}</p>
            <p className={styles.queHacer}>{t.queHacer}</p>
          </div>
        );
      })()}
      {resultado?.ok && <div className={styles.exito}>{resultado.detalle}</div>}

      <section className={styles.panel}>
        <h3 className={styles.panelTitulo}>Lo que se guardó antes</h3>
        {historial.length === 0 && <p className={styles.vacio}>Todavía no hay nada guardado.</p>}
        <ul className={styles.historial}>
          {historial.map((c) => (
            <li key={c.sha}>
              <span className={styles.sha}>{c.sha_corto}</span> {c.asunto}
              <span className={styles.autor}> — {c.autor}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
