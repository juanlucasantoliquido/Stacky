/**
 * GitlabEngineSwitch.tsx — Plan 290 F5: el master switch de GitLab, desde la
 * interfaz y EN CALIENTE.
 *
 * Era la última perilla de GitLab que exigía editar un archivo a mano y
 * reiniciar. Hoy se enciende de costado, al crear un proyecto GitLab
 * (`api/projects.py:141-142`), y no hay ninguna pantalla que la muestre —
 * `services/setup_guides.py:147` ya lo denunciaba por escrito.
 *
 * Va por `/api/global-config` y NO por el panel de configuración: esa clave ya
 * vive en `_MANAGED_KEYS` (`api/global_config.py:82`) desde el Plan 65, y
 * registrarla además como flag crearía DOS escritores del mismo valor — el
 * defecto que ese mismo archivo documenta para LOG_LEVEL con la frase "UN solo
 * escritor". Mismo criterio y mismo patrón que `LogLevelPanel`.
 *
 * Los clientes crudos (`rawGet`/`rawPut`) se importan de `api/client` igual que
 * los usa `LogLevel`: no lanzan en non-2xx, que es lo que hace falta para
 * distinguir un 400 de un backend caído.
 */
import { useEffect, useState } from "react";
import { GitBranch } from "lucide-react";
import { rawGet, rawPut } from "../api/client";
import {
  avisoDeApagado,
  estaEncendido,
  valorParaGuardar,
} from "../services/gitlabEngineModel";
import { Select } from "./ui";
import styles from "./GitlabEngineSwitch.module.css";

const CLAVE = "STACKY_GITLAB_ENABLED";

interface RespuestaPut {
  ok?: boolean;
  persisted?: boolean;
  message?: string;
  error?: string;
}

export default function GitlabEngineSwitch() {
  const [encendido, setEncendido] = useState<boolean | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    rawGet<{ ok?: boolean; config?: Record<string, unknown> }>("/api/global-config")
      .then((res) => {
        if (cancelado) return;
        setEncendido(estaEncendido(res.data?.config?.[CLAVE]));
      })
      .catch(() => {
        /* el panel se muestra igual, sin estado resuelto */
      });
    return () => {
      cancelado = true;
    };
  }, []);

  const aplicar = (valor: string) => {
    const nuevo = valor === "si";
    setEncendido(nuevo);
    setGuardando(true);
    setOk(null);
    setError(null);
    rawPut<RespuestaPut>("/api/global-config", { [CLAVE]: valorParaGuardar(nuevo) })
      .then((res) => {
        if (!res.ok) {
          setError(res.errorBody?.error ?? `No se pudo aplicar el cambio (${res.status}).`);
          return;
        }
        setOk(
          res.data?.persisted === false
            ? res.data?.message ??
                "Aplicado, pero no se pudo guardar: no sobrevive al reinicio."
            : "Aplicado sin reiniciar y guardado."
        );
      })
      .catch(() => setError("No se pudo aplicar el cambio."))
      .finally(() => setGuardando(false));
  };

  const aviso = encendido === null ? null : avisoDeApagado(encendido);

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <GitBranch size={16} />
        <h2 className={styles.title}>Motor de GitLab</h2>
      </div>

      <div className={styles.row}>
        <label htmlFor="stacky-gitlab-enabled">Habilitado:</label>
        <Select
          id="stacky-gitlab-enabled"
          className={styles.control}
          value={encendido === null ? "" : encendido ? "si" : "no"}
          disabled={guardando || encendido === null}
          onChange={(e) => aplicar(e.target.value)}
        >
          <option value="" disabled>
            Cargando…
          </option>
          <option value="si">Sí</option>
          <option value="no">No</option>
        </Select>
      </div>

      {aviso ? <p className={styles.aviso}>{aviso}</p> : null}
      {ok ? <p className={styles.okLine}>{ok}</p> : null}
      {error ? <p className={styles.errorLine}>{error}</p> : null}

      <p className={styles.muted}>
        El cambio se aplica al instante, sin reiniciar el servicio, y queda guardado
        para el próximo arranque.
      </p>
    </div>
  );
}
