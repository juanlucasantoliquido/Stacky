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
import { Tickets } from "../api/endpoints";

export interface UseTicketSyncOptions {
  intervalMs?: number;
  syncOnMount?: boolean;
  respectVisibility?: boolean;
}

export interface UseTicketSyncResult {
  lastSyncedAt: string | null;
  secondsSinceSync: number | null;
  isSyncing: boolean;
  syncError: string | null;
  triggerSync: () => void;
  isStale: boolean;
  consecutiveErrors: number;
}

const DEFAULT_INTERVAL_MS = 45_000;
const MAX_BACKOFF_MS = 5 * 60_000; // 5 minutos

export function useTicketSync(options: UseTicketSyncOptions = {}): UseTicketSyncResult {
  const {
    intervalMs = DEFAULT_INTERVAL_MS,
    syncOnMount = true,
    respectVisibility = true,
  } = options;

  const queryClient = useQueryClient();
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [consecutiveErrors, setConsecutiveErrors] = useState(0);
  const [, setTick] = useState(0); // para forzar re-render del reloj

  // Refs para evitar closures obsoletas en los efectos
  const consecutiveErrorsRef = useRef(0);
  const lastSyncedAtRef = useRef<string | null>(null);
  const intervalMsRef = useRef(intervalMs);
  intervalMsRef.current = intervalMs;

  // Calculo de segundos desde el ultimo sync (con re-render cada segundo)
  useEffect(() => {
    const ticker = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(ticker);
  }, []);

  const secondsSinceSync: number | null = lastSyncedAt
    ? Math.floor((Date.now() - new Date(lastSyncedAt).getTime()) / 1000)
    : null;

  const isStale = secondsSinceSync !== null && secondsSinceSync * 1000 > intervalMs * 2;

  // Mutacion de sync
  const syncMutation = useMutation({
    mutationFn: () => {
      const headers: Record<string, string> = {
        "X-Stacky-Trigger": "auto_poll",
      };
      return fetch(
        `${(window as any).__STACKY_API_BASE__ ?? ""}/api/tickets/sync-v2`,
        { method: "POST", headers }
      ).then(r => r.json());
    },
    onSuccess: (data) => {
      if (data.ok || data.synced_at) {
        const syncedAt = data.synced_at ?? new Date().toISOString();
        setLastSyncedAt(syncedAt);
        lastSyncedAtRef.current = syncedAt;
        setSyncError(null);
        consecutiveErrorsRef.current = 0;
        setConsecutiveErrors(0);
        // Invalidar queries de tickets para que se refresquen
        queryClient.invalidateQueries({ queryKey: ["tickets"] });
        queryClient.invalidateQueries({ queryKey: ["tickets-hierarchy"] });
      } else if (data.error === "rate_limited") {
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
  });

  const triggerSync = useCallback(() => {
    if (!syncMutation.isPending) {
      syncMutation.mutate();
    }
  }, [syncMutation]);

  // Cargar lastSyncedAt inicial desde el endpoint de status
  useEffect(() => {
    Tickets.syncStatus()
      .then((data) => {
        if (data.last_synced_at) {
          setLastSyncedAt(data.last_synced_at);
          lastSyncedAtRef.current = data.last_synced_at;
        }
      })
      .catch(() => {/* ignorar — no critico */});
  }, []);

  // Sync en mount
  useEffect(() => {
    if (syncOnMount) {
      // Delay minimo para evitar colision con mount inicial
      const t = setTimeout(() => triggerSync(), 500);
      return () => clearTimeout(t);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
        triggerSync();
        scheduleNext();
      }, delay);
    };

    scheduleNext();

    return () => clearTimeout(timerId);
  }, [respectVisibility, triggerSync]);

  // Page Visibility API: sync inmediato al volver a la tab si estuvo oculta
  useEffect(() => {
    if (!respectVisibility) return;

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        const secs = lastSyncedAtRef.current
          ? Math.floor((Date.now() - new Date(lastSyncedAtRef.current).getTime()) / 1000)
          : null;
        if (secs === null || secs * 1000 > intervalMsRef.current) {
          triggerSync();
        }
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [respectVisibility, triggerSync]);

  return {
    lastSyncedAt,
    secondsSinceSync,
    isSyncing: syncMutation.isPending,
    syncError,
    triggerSync,
    isStale,
    consecutiveErrors,
  };
}
