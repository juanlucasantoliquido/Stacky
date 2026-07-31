import { useCallback, useEffect, useState } from "react";
import { Tickets } from "../api/endpoints";
import { userFacingMessage } from "../api/gatewayError";
import { getBoolFlag, readCachedBoolFlag } from "../services/flagGate";
import {
  FLAG_PUBLICAR_ETIQUETAS,
  alternarSeleccion,
  esPublicable,
  estadoBotonPublicar,
  resumenBackfill,
  seleccionInicialBackfill,
  type CambioBackfill,
  type PlanBackfill,
} from "../lib/jerarquiaLocal";
import { Button, Checkbox } from "./ui";

/**
 * Plan 277 F5 — publicar en el GitLab de la empresa, como etiquetas reales, la
 * clasificación que el operador hizo dentro de Stacky.
 *
 * EL ORDEN DEL FLUJO ES EL PUNTO: ver el diff → elegir → confirmar. Es la única
 * acción del plan que modifica el sistema del operador, sobre issues que Stacky no
 * creó, así que nada se escribe sin que él haya visto antes qué se toca y haya
 * marcado ítem por ítem. Ver el diff NO necesita la flag (es read-only); publicar sí.
 *
 * Toda la lógica verificable (qué es publicable, qué se preselecciona, qué dice el
 * aviso del botón) vive en `lib/jerarquiaLocal.ts` porque este repo no tiene RTL ni
 * jsdom: acá queda el render y el envío, que se cubren con el smoke manual de 6 pasos.
 */
export interface PublicarEtiquetasGitLabProps {
  projectName?: string | null;
  /** Solo se muestra en proyectos GitLab: en ADO no hay etiquetas que publicar. */
  trackerType?: string | null;
  /** Se llama tras publicar, para refrescar el grafo. */
  onPublicado?: () => void;
}

export default function PublicarEtiquetasGitLab({
  projectName,
  trackerType,
  onPublicado,
}: PublicarEtiquetasGitLabProps) {
  const [flagOn, setFlagOn] = useState(() => readCachedBoolFlag(FLAG_PUBLICAR_ETIQUETAS));
  useEffect(() => {
    let vivo = true;
    getBoolFlag(FLAG_PUBLICAR_ETIQUETAS).then((on) => {
      if (vivo) setFlagOn(on);
    });
    return () => {
      vivo = false;
    };
  }, []);

  const [plan, setPlan] = useState<PlanBackfill | null>(null);
  const [seleccion, setSeleccion] = useState<number[]>([]);
  const [cargando, setCargando] = useState(false);
  const [publicando, setPublicando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<string | null>(null);

  const verDiff = useCallback(async () => {
    setCargando(true);
    setError(null);
    setResultado(null);
    try {
      const data = await Tickets.backfillPlan(projectName ?? null);
      setPlan(data);
      // Preselección: todo lo publicable. Lo que está en conflicto queda afuera.
      setSeleccion(seleccionInicialBackfill(data));
    } catch (e) {
      setError(userFacingMessage(e).title);
    } finally {
      setCargando(false);
    }
  }, [projectName]);

  const publicar = useCallback(async () => {
    setPublicando(true);
    setError(null);
    setResultado(null);
    try {
      const r = await Tickets.backfillApply(projectName ?? null, seleccion);
      const partes = [`Se escribieron ${r.escritos} en GitLab.`];
      if (r.omitidos) partes.push(`${r.omitidos} sin tocar.`);
      if (r.fallidos.length) partes.push(`Falló el ticket ${r.fallidos[0].ado_id}: ${r.fallidos[0].error}`);
      if (r.pendientes.length) partes.push(`Quedaron ${r.pendientes.length} sin intentar.`);
      setResultado(partes.join(" "));
      // El diff quedó viejo: lo que se escribió ya no tiene nada que agregar.
      await verDiff();
      onPublicado?.();
    } catch (e) {
      setError(userFacingMessage(e).title);
    } finally {
      setPublicando(false);
    }
  }, [onPublicado, projectName, seleccion, verDiff]);

  if ((trackerType ?? "").toLowerCase() !== "gitlab") return null;

  const boton = estadoBotonPublicar(flagOn, seleccion, publicando);
  const resumen = plan ? resumenBackfill(plan) : null;

  const rotuloDe = (c: CambioBackfill) => {
    if (c.conflicto) {
      return c.error
        ? `no se pudo leer en GitLab (${c.error}) — no se toca`
        : `GitLab ya dice ${c.ya_tiene.join(", ") || "otra cosa"} — manda GitLab, no se toca`;
    }
    if (!c.agregar.length) return "ya tiene todo lo que le corresponde";
    return `agregar ${c.agregar.join(", ")}`;
  };

  return (
    <div>
      <Button size="sm" onClick={verDiff} disabled={cargando || publicando}>
        {cargando ? "Buscando…" : "Ver qué se va a cambiar"}
      </Button>
      <Button
        size="sm"
        variant="primary"
        onClick={publicar}
        disabled={!boton.habilitado}
        title={boton.hint || undefined}
      >
        {boton.rotulo}
      </Button>
      {!flagOn && <p role="note">{boton.hint}</p>}
      {error && <p role="alert">{error}</p>}
      {resultado && <p role="status">{resultado}</p>}

      {resumen && (
        <p>
          {resumen.total} tickets clasificados en Stacky: {resumen.publicables} para publicar,{" "}
          {resumen.conflictos} en conflicto (manda GitLab) y {resumen.sinCambios} que ya están.
          Solo se AGREGAN etiquetas: las que el ticket ya tenía quedan intactas.
        </p>
      )}

      {plan && (
        <ul>
          {plan.cambios.map((c) => (
            <li key={`${c.ado_id}`}>
              <Checkbox
                label={`#${c.iid} ${c.title} — ${rotuloDe(c)}`}
                checked={seleccion.includes(c.ado_id)}
                disabled={!esPublicable(c) || publicando}
                onChange={() => setSeleccion((s) => alternarSeleccion(s, c))}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
