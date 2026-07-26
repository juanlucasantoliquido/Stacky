import { useEffect, useRef } from "react";

import { shortcutRegistry, type ShortcutDef } from "../services/shortcuts";

/**
 * Plan 172 F2 — Registra un atajo mientras el componente esté montado.
 *
 * El handler se lee por REF en cada disparo: si se capturara por closure, el
 * atajo seguiría llamando a la versión vieja del handler y el operador vería
 * la tecla "funcionar" sobre estado viejo, que es peor que no funcionar.
 *
 * Re-registrar por id es idempotente, así el doble montaje de StrictMode
 * (register → cleanup → register) no duplica nada.
 */
export function useShortcut(def: ShortcutDef): void {
  const ref = useRef(def);
  ref.current = def;
  useEffect(() => {
    shortcutRegistry.register({ ...ref.current, handler: () => ref.current.handler?.() });
    const id = ref.current.id;
    return () => shortcutRegistry.unregister(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [def.id]);
}

export default useShortcut;
