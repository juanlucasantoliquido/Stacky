/**
 * LogLevelPanel.tsx — Plan 257 F4: el nivel de detalle del registro, desde la
 * interfaz y EN CALIENTE.
 *
 * Era la única configuración del operador que exigía editar un archivo a mano y
 * reiniciar el servicio, perdiendo cualquier corrida en vuelo. Eso viola el
 * riel duro "toda configuración del operador se cambia desde la interfaz".
 *
 * NO es una flag del panel de configuración a propósito: ese panel solo guarda
 * el valor y no ejecuta efectos, así que diría "aplicado" mientras el registro
 * sigue igual — un falso verde nuevo. Va por un único camino que sí aplica.
 */
import { useEffect, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { LogLevel, LOG_LEVELS, type LogLevelName } from "../api/endpoints";
import { Select } from "./ui";
import styles from "./LogLevelPanel.module.css";

export default function LogLevelPanel() {
  const [nivel, setNivel] = useState<LogLevelName | "">("");
  const [guardando, setGuardando] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    LogLevel.get()
      .then((actual) => {
        if (!cancelado && actual) setNivel(actual);
      })
      .catch(() => {
        /* el panel se muestra igual con el selector vacío */
      });
    return () => {
      cancelado = true;
    };
  }, []);

  const aplicar = (valor: string) => {
    const elegido = valor as LogLevelName;
    setNivel(elegido);
    setGuardando(true);
    setOk(null);
    setError(null);
    LogLevel.set(elegido)
      .then((res) => {
        if (!res.ok) {
          setError(res.error ?? "No se pudo aplicar el nivel.");
          return;
        }
        setOk(
          res.persisted === false
            ? res.message ?? "Aplicado, pero no se pudo guardar: no sobrevive al reinicio."
            : "Aplicado sin reiniciar y guardado."
        );
      })
      .catch(() => setError("No se pudo aplicar el nivel."))
      .finally(() => setGuardando(false));
  };

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <SlidersHorizontal size={16} />
        <h2 className={styles.title}>Nivel de detalle del registro</h2>
      </div>

      <div className={styles.row}>
        <label htmlFor="stacky-log-level">Registrar desde:</label>
        <Select
          id="stacky-log-level"
          className={styles.control}
          value={nivel}
          disabled={guardando}
          onChange={(e) => aplicar(e.target.value)}
        >
          <option value="" disabled>
            Seleccioná un nivel
          </option>
          {LOG_LEVELS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </Select>
      </div>

      {nivel === "DEBUG" ? (
        <p className={styles.aviso}>
          El nivel de máximo detalle genera mucho volumen. Acordate de volver a INFO
          cuando termines de diagnosticar.
        </p>
      ) : null}

      {ok ? <p className={styles.okLine}>{ok}</p> : null}
      {error ? <p className={styles.errorLine}>{error}</p> : null}

      <p className={styles.muted}>
        El cambio se aplica al instante, sin reiniciar el servicio ni cortar las
        corridas en vuelo, y queda guardado para el próximo arranque.
      </p>
    </div>
  );
}
