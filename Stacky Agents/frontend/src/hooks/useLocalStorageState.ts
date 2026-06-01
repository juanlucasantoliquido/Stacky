import { useCallback, useEffect, useState } from "react";

/**
 * useLocalStorageState — estado de React persistido en localStorage.
 *
 * Plan 2026-05-27 (principio de "persistencia local de UX"): todo filtro,
 * checkbox o preferencia de la vista debe sobrevivir entre sesiones sin
 * reconfiguración manual. Este hook rehidrata el valor inicial desde
 * localStorage y lo re-escribe ante cada cambio.
 *
 * Es tolerante a fallos: si localStorage no está disponible (modo privado,
 * cuota llena) cae a estado en memoria sin romper la app.
 */
export function useLocalStorageState<T>(
  key: string,
  defaultValue: T
): [T, (value: T | ((prev: T) => T)) => void] {
  const [state, setState] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw !== null) return JSON.parse(raw) as T;
    } catch {
      /* ignore: cae al default */
    }
    return defaultValue;
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(state));
    } catch {
      /* ignore: persistencia best-effort */
    }
  }, [key, state]);

  const set = useCallback((value: T | ((prev: T) => T)) => {
    setState(value);
  }, []);

  return [state, set];
}

export default useLocalStorageState;
