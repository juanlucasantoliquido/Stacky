/**
 * useTicketSync — Hook de sincronizacion automatica con ADO.
 *
 * P7: Encapsula la logica de polling, forzado de sync en mount,
 * Page Visibility API y backoff exponencial ante errores.
 *
 * Caracteristicas:
 * - intervalMs configurable (default: 45_000 ms)
 * - Pausa el polling cuando la tab esta oculta (Page Visibility API)
 * - Al volver a la tab, si pasaron mas de intervalMs, hace sync inmediato
 * - Backoff exponencial si ADO devuelve error (hasta 5 minutos)
 * - triggerSync() para sync manual (respeta rate limit del backend)
 * - isStale: true si lastSyncedAt > 2 * intervalMs
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Tickets, type TicketSyncResult } from "../api/endpoints";
import { apiBase } from "../api/client";
import { useWorkbench } from "../store/workbench";

export interface UseTicketSyncOptions {
  intervalMs?: number;
  syncOnMount?: boolean;
  respectVisibility?: boolean;
}

export interface UseTicketSyncResult {
  lastSyncedAt: string | null;
  isSyncing: boolean;
  syncError: string | null;
  triggerSync: () => void;
  consecutiveErrors: number;
}

/** Plan 156 F4 (C5) — intervalo real del sync. El reloj de "hace Xs"/stale vive
 *  ahora en la hoja SyncStatusBar; ésta es la constante de la que deriva el
 *  umbral de stale (intervalMs*2). TicketBoard la usa para AMBOS (hook + hoja)
 *  para que el umbral quede idéntico al de antes (no un mágico distinto). */
export const DEFAULT_INTERVAL_MS = 45_000;
const MAX_BACKOFF_MS = 5 * 60_000; // 5 minutos

/** Plan 276 F6 — payload de `POST /api/tickets/sync-v2` tal como lo lee este hook.
 *  `available` lo pone el envelope de capacidad degradada (plan 218): un tracker que
 *  NO soporta sincronización responde 200 con `available:false`. */
export type TicketSyncPayload = TicketSyncResult & {
  idempotent?: boolean;
  available?: boolean;
};

/** Plan 276 F6 — clasifica la respuesta del sync en las 4 situaciones reales.
 *
 * `available: false` se evalúa PRIMERO y a propósito: el envelope de capacidad
 * degradada devuelve `{ok: true, available: false}`, así que preguntar por `ok`
 * antes clasificaría una carencia DECLARADA como éxito. Ése es el peor modo de
 * falla del sistema: "sincronizado hace 2s", cero tickets y cero error.
 */
export function clasificarRespuestaDeSync(
  data: { ok?: boolean; synced_at?: string; available?: boolean; error?: string },
): "exito" | "carencia" | "rate_limited" | "error" {
  if (data.available === false) return "carencia";
  if (data.ok || data.synced_at) return "exito";
  if (data.error === "rate_limited") return "rate_limited";
  return "error";
}

/** Plan 276 F6/C3 — decide si hay que refetchear las queries de tickets.
 *
 * Un sync MANUAL invalida SIEMPRE, aunque el backend responda idempotente: el
 * operador acaba de pedir explícitamente "traeme los tickets" y la causa más
 * común de un idempotente manual es que las filas YA ESTÁN en la BD y la vista
 * está desactualizada. No refetchear ahí deja la pantalla vacía con los datos
 * cargados, que es indistinguible de "el sync no anda".
 *
 * Es una LECTURA de la BD local: no quema tokens en reposo (categoría A no
 * aplica: no hay loop, no hay modelo) y no escribe en ningún sistema del
 * operador (categoría B no aplica). Va ON, sin flag nueva.
 */
export function debeRefrescarQueriesDeTickets(
  data: { idempotent?: boolean; created?: number; updated?: number; removed?: number },
  trigger: "manual" | "auto_poll" | "startup",
): boolean {
  if (trigger === "manual") return true;
  if (data.idempotent === true) return false;
  return Boolean((data.created ?? 0) || (data.updated ?? 0) || (data.removed ?? 0));
}

export function useTicketSync(options: UseTicketSyncOptions = {}): UseTicketSyncResult {
  const {
    intervalMs = DEFAULT_INTERVAL_MS,
    syncOnMount = true,
    respectVisibility = true,
  } = options;

  const queryClient = useQueryClient();
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [consecutiveErrors, setConsecutiveErrors] = useState(0);
  const [showForegroundSync, setShowForegroundSync] = useState(false);
  const [statusReady, setStatusReady] = useState(false);

  // Refs para evitar closures obsoletas en los efectos
  const consecutiveErrorsRef = useRef(0);
  const lastSyncedAtRef = useRef<string | null>(null);
  const intervalMsRef = useRef(intervalMs);
  const lastTriggerRef = useRef<"manual" | "auto_poll" | "startup">("auto_poll");
  intervalMsRef.current = intervalMs;

  // Plan 156 F4 — el tic-tac de 1s (antes aquí, re-renderizaba TicketBoard
  // entero 60×/min) se movió a la hoja SyncStatusBar. Este hook ya no calcula
  // secondsSinceSync/isStale ni fuerza re-render por segundo; solo expone
  // lastSyncedAt, del que la hoja deriva "hace Xs"/stale localmente.

  // Plan 276 F6/C3 — `shouldRefreshTicketQueries` vivía acá como CLOSURE sin
  // export: era intesteable sin montar el componente y en este repo no hay RTL ni
  // jsdom. Ahora es `debeRefrescarQueriesDeTickets`, a nivel de módulo y exportada.

  // Mutacion de sync
  const syncMutation = useMutation({
    mutationFn: (trigger: "manual" | "auto_poll" | "startup" = "auto_poll") => {
      const headers: Record<string, string> = {
        "X-Stacky-Trigger": trigger,
      };
      return fetch(
        `${apiBase}/api/tickets/sync-v2`,
        {
          method: "POST",
          headers,
          body: JSON.stringify(activeProjectName ? { project: activeProjectName } : {}),
        }
      ).then(async r => {
        const text = await r.text().catch(() => "");
        if (!text) return { ok: r.ok, status: r.status };
        try { return JSON.parse(text); }
        catch { throw new Error(`Respuesta no-JSON del servidor (HTTP ${r.status})`); }
      });
    },
    onSuccess: (data: TicketSyncPayload) => {
      const clase = clasificarRespuestaDeSync(data);
      if (clase === "carencia") {
        // Plan 276 F6 — `available: false` es una carencia declarada, NUNCA un
        // éxito: sin esta guarda la UI muestra "sincronizado hace 2s" con cero
        // tickets y cero error.
        setSyncError(
          data.message || "El tracker de este proyecto no soporta sincronización."
        );
      } else if (clase === "exito") {
        const syncedAt = data.synced_at ?? new Date().toISOString();
        setLastSyncedAt(syncedAt);
        lastSyncedAtRef.current = syncedAt;
        setSyncError(null);
        consecutiveErrorsRef.current = 0;
        setConsecutiveErrors(0);
        if (debeRefrescarQueriesDeTickets(data, lastTriggerRef.current)) {
          queryClient.invalidateQueries({ queryKey: ["ticket-sync", activeProjectName] });
          queryClient.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
          queryClient.invalidateQueries({ queryKey: ["tickets-hierarchy", activeProjectName] });
        }
      } else if (clase === "rate_limited") {
        // Rate limited — no es error, solo esperar
        setSyncError(null);
      } else {
        const msg = data.message || "Error de sincronizacion";
        setSyncError(msg);
        consecutiveErrorsRef.current += 1;
        setConsecutiveErrors(consecutiveErrorsRef.current);
      }
    },
    onError: (err: Error) => {
      setSyncError(err.message || "Error de red al sincronizar");
      consecutiveErrorsRef.current += 1;
      setConsecutiveErrors(consecutiveErrorsRef.current);
    },
    onSettled: () => {
      setShowForegroundSync(false);
    },
  });

  const requestSync = useCallback((
    trigger: "manual" | "auto_poll" | "startup",
    foreground = false,
  ) => {
    if (syncMutation.isPending) return;
    lastTriggerRef.current = trigger;
    setShowForegroundSync(foreground);
    syncMutation.mutate(trigger);
  }, [syncMutation]);

  const triggerSync = useCallback(() => {
    requestSync("manual", true);
  }, [requestSync]);

  // Cargar lastSyncedAt inicial desde el endpoint de status
  useEffect(() => {
    setLastSyncedAt(null);
    lastSyncedAtRef.current = null;
    setSyncError(null);
    setShowForegroundSync(false);
    setStatusReady(false);
    consecutiveErrorsRef.current = 0;
    setConsecutiveErrors(0);
    Tickets.syncStatus(activeProjectName)
      .then((data) => {
        if (data.last_synced_at) {
          setLastSyncedAt(data.last_synced_at);
          lastSyncedAtRef.current = data.last_synced_at;
        }
      })
      .catch(() => {/* ignorar — no critico */})
      .finally(() => setStatusReady(true));
  }, [activeProjectName]);

  // Sync en mount
  useEffect(() => {
    if (!syncOnMount || !statusReady) return;

    const last = lastSyncedAtRef.current;
    const shouldSync =
      !last ||
      (Date.now() - new Date(last).getTime()) > intervalMsRef.current;

    if (!shouldSync) return;

    const t = setTimeout(() => {
      requestSync("startup", false);
    }, 1500);
    return () => clearTimeout(t);
  }, [activeProjectName, requestSync, statusReady, syncOnMount]);

  // Polling con backoff exponencial
  useEffect(() => {
    const getEffectiveInterval = () => {
      const errors = consecutiveErrorsRef.current;
      if (errors === 0) return intervalMsRef.current;
      return Math.min(intervalMsRef.current * Math.pow(2, errors), MAX_BACKOFF_MS);
    };

    let timerId: ReturnType<typeof setTimeout>;

    const scheduleNext = () => {
      const delay = getEffectiveInterval();
      timerId = setTimeout(() => {
        // Si la tab esta oculta y respectVisibility activo, no hacer sync
        if (respectVisibility && document.visibilityState === "hidden") {
          scheduleNext();
          return;
        }
        requestSync("auto_poll", false);
        scheduleNext();
      }, delay);
    };

    scheduleNext();

    return () => clearTimeout(timerId);
  }, [requestSync, respectVisibility]);

  // Page Visibility API: sync inmediato al volver a la tab si estuvo oculta
  useEffect(() => {
    if (!respectVisibility) return;

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        const secs = lastSyncedAtRef.current
          ? Math.floor((Date.now() - new Date(lastSyncedAtRef.current).getTime()) / 1000)
          : null;
        if (secs === null || secs * 1000 > intervalMsRef.current) {
          requestSync("auto_poll", false);
        }
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [requestSync, respectVisibility]);

  return {
    lastSyncedAt,
    isSyncing: syncMutation.isPending && showForegroundSync,
    syncError,
    triggerSync,
    consecutiveErrors,
  };
}
