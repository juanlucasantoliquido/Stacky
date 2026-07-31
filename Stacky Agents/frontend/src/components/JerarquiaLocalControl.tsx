import { useCallback, useEffect, useState } from "react";
import { Tickets } from "../api/endpoints";
import { userFacingMessage } from "../api/gatewayError";
import { getBoolFlag, readCachedBoolFlag } from "../services/flagGate";
import {
  FLAG_JERARQUIA_LOCAL,
  TIPOS_CANONICOS_JERARQUIA,
  debeMostrarControlJerarquia,
  valorInicialPadre,
  validarPadre,
  type TicketJerarquiaLocal,
} from "../lib/jerarquiaLocal";
import { Button, Field, Input, Select } from "./ui";

/**
 * Plan 277 F4 — el operador dice de qué tipo es un ticket de GitLab y de cuál otro
 * cuelga, SIN escribir una sola letra en el GitLab de la empresa.
 *
 * Toda la lógica verificable (¿se muestra?, ¿el número es válido?) vive en
 * `lib/jerarquiaLocal.ts` porque este repo no tiene RTL ni jsdom: acá queda solo el
 * render y el envío. Los controles son las primitivas de `components/ui` —no tags
 * crudos— y no hay estilos escritos a mano en el marcado: los dos ratchets de deuda
 * de frontend cuentan por archivo y solo admiten que la deuda baje.
 */
export interface JerarquiaLocalControlProps {
  ticket: TicketJerarquiaLocal & { id: number };
  /** Se llama tras un guardado exitoso, para refrescar el tablero y el grafo. */
  onGuardado?: () => void;
}

export default function JerarquiaLocalControl({ ticket, onGuardado }: JerarquiaLocalControlProps) {
  // Lectura sincrónica desde el cache (anti-flash) + confirmación asíncrona.
  const [flagOn, setFlagOn] = useState(() => readCachedBoolFlag(FLAG_JERARQUIA_LOCAL));
  useEffect(() => {
    let vivo = true;
    getBoolFlag(FLAG_JERARQUIA_LOCAL).then((on) => {
      if (vivo) setFlagOn(on);
    });
    return () => {
      vivo = false;
    };
  }, []);

  // Precargados con lo que el operador ya guardó (echo-back de `to_dict()`).
  const [tipo, setTipo] = useState(ticket.local_work_item_type ?? "");
  const [padre, setPadre] = useState(() => valorInicialPadre(ticket));
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const guardar = useCallback(async () => {
    const validado = validarPadre(padre, ticket);
    if (!validado.ok) {
      setError(validado.mensaje);
      setOk(false);
      return;
    }
    setGuardando(true);
    setError(null);
    setOk(false);
    try {
      // Se mandan las DOS claves porque las dos son editables en este control; el
      // string vacío viaja como `null`, que es el borrado explícito del servidor.
      await Tickets.setLocalHierarchy(ticket.id, {
        work_item_type: tipo === "" ? null : tipo,
        parent_iid: validado.valor,
      });
      setOk(true);
      onGuardado?.();
    } catch (e) {
      setError(userFacingMessage(e).title);
    } finally {
      setGuardando(false);
    }
  }, [onGuardado, padre, ticket, tipo]);

  if (!debeMostrarControlJerarquia(ticket, flagOn)) return null;

  return (
    <div>
      <Field label="Tipo (solo en Stacky)">
        {(ctl) => (
          <Select
            {...ctl}
            value={tipo}
            disabled={guardando}
            onChange={(e) => {
              setTipo(e.target.value);
              setOk(false);
            }}
          >
            <option value="">Sin clasificar</option>
            {TIPOS_CANONICOS_JERARQUIA.map((t) => (
              <option key={t.valor} value={t.valor}>
                {t.rotulo}
              </option>
            ))}
          </Select>
        )}
      </Field>

      <Field
        label="Cuelga del ticket número"
        help="Dejalo vacío para que no cuelgue de ninguno."
        error={error ?? undefined}
      >
        {(ctl) => (
          <Input
            {...ctl}
            value={padre}
            inputMode="numeric"
            placeholder="por ejemplo 42"
            disabled={guardando}
            onChange={(e) => {
              setPadre(e.target.value);
              setError(null);
              setOk(false);
            }}
          />
        )}
      </Field>

      <Button size="sm" onClick={guardar} disabled={guardando}>
        {guardando ? "Guardando…" : "Guardar clasificación"}
      </Button>
      {ok && <span role="status"> Guardado. No se modificó nada en GitLab.</span>}
    </div>
  );
}
