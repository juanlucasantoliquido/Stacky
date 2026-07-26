import { useCallback, useEffect, useState } from "react";

import type { EntityAction } from "../../services/entityActions";

interface MenuAbierto {
  x: number;
  y: number;
  actions: EntityAction[];
  byKeyboard: boolean;
}

/**
 * Plan 175 F3 — Instancia el menú contextual en una página.
 *
 * Devuelve los props para la fila y el estado del menú. La página decide QUÉ
 * acciones tiene cada entidad; esto solo se ocupa de dónde y cuándo abrirlo.
 */
export function useEntityContextMenu(enabled: boolean) {
  const [abierto, setAbierto] = useState<MenuAbierto | null>(null);

  const cerrar = useCallback(() => setAbierto(null), []);

  // Scrollear con el menú abierto lo dejaría flotando lejos de su fila.
  useEffect(() => {
    if (!abierto) return;
    window.addEventListener("scroll", cerrar, true);
    return () => window.removeEventListener("scroll", cerrar, true);
  }, [abierto, cerrar]);

  const rowProps = useCallback(
    (actions: EntityAction[]) => {
      if (!enabled) return {};
      return {
        onContextMenu: (ev: React.MouseEvent) => {
          ev.preventDefault();
          setAbierto({ x: ev.clientX, y: ev.clientY, actions, byKeyboard: false });
        },
        onKeyDown: (ev: React.KeyboardEvent) => {
          // La tecla de menú contextual y Shift+F10 son el equivalente de teclado
          // del clic derecho: sin ellas, el menú es inaccesible sin mouse.
          if (ev.key !== "ContextMenu" && !(ev.key === "F10" && ev.shiftKey)) return;
          ev.preventDefault();
          const caja = (ev.currentTarget as HTMLElement).getBoundingClientRect();
          setAbierto({ x: caja.left, y: caja.bottom, actions, byKeyboard: true });
        },
      };
    },
    [enabled],
  );

  return { menu: abierto, cerrar, rowProps };
}

export default useEntityContextMenu;
