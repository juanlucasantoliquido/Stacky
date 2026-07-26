// Plan 173 F2 — El ÚNICO módulo de esta serie con efectos: localStorage + red.
//
// Estrategia: localStorage responde YA (sin esperar a la red) y el backend gana
// al hidratar. Así las vistas sobreviven a limpiar el navegador o a cambiar de
// máquina, pero la pantalla nunca se queda esperando para pintar.
//
// REGLA DURA: acá se usa `fetch` CRUDO, nunca el wrapper api.* — ese wrapper
// LANZA en toda respuesta non-2xx (404 con la flag apagada, 400/413 de
// validación), lo que rompería el fire-and-forget y el fallback silencioso.

import { useEffect, useState } from "react";

const LS_PREFIX = "stacky.ui.prefs.";
const API_BASE = "/api/preferences/ui/";

export function loadUiPrefLocal<T>(key: string, fallback: T): T {
  try {
    const crudo = localStorage.getItem(LS_PREFIX + key);
    return crudo == null ? fallback : (JSON.parse(crudo) as T);
  } catch {
    // Modo privado, cuota llena o JSON viejo corrupto: la pantalla arranca con
    // el default en vez de romperse.
    return fallback;
  }
}

export function saveUiPref(key: string, value: unknown): void {
  try {
    localStorage.setItem(LS_PREFIX + key, JSON.stringify(value));
  } catch {
    // Sin localStorage igual se intenta el backend: perder la persistencia
    // local no debería perder también la remota.
  }
  // Fire-and-forget: guardar una preferencia no puede bloquear ni fallar a la
  // vista. Si el backend no está, queda lo local.
  void fetch(API_BASE + encodeURIComponent(key), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  }).catch(() => {});
}

/** Trae del backend y pisa lo local. `null` = no hay nada remoto (o no se pudo
 *  leer): el caller CONSERVA lo que tenía, no lo borra. */
export async function hydrateUiPref<T>(
  key: string,
  sanitize: (raw: unknown) => T,
): Promise<T | null> {
  try {
    const res = await fetch(API_BASE + encodeURIComponent(key));
    if (!res.ok) return null;
    const body = await res.json();
    if (body?.value == null) return null;
    const limpio = sanitize(body.value);
    try {
      localStorage.setItem(LS_PREFIX + key, JSON.stringify(limpio));
    } catch {
      /* sin localStorage se sigue igual */
    }
    return limpio;
  } catch {
    return null;
  }
}

let _healthPromise: Promise<boolean> | null = null;

/** Hook de la flag. Optimista en `true` porque el default es ON: apagarla es
 *  excepcional, y asumir OFF haría parpadear la barra en el caso normal. */
export function useSavedViewsEnabled(): boolean {
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    let vivo = true;
    // Una sola consulta por sesión, compartida por todas las pantallas.
    _healthPromise ??= fetch("/api/diag/health")
      .then((r) => (r.ok ? r.json() : null))
      // Solo un `false` EXPLÍCITO apaga: un backend viejo sin el campo, o un
      // fetch que falla, no pueden apagar una feature que está ON por default.
      .then((d) => d?.ui_saved_views_enabled !== false)
      .catch(() => true);
    void _healthPromise.then((v) => {
      if (vivo) setEnabled(v);
    });
    return () => {
      vivo = false;
    };
  }, []);

  return enabled;
}
