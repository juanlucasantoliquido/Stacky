import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Executions } from "../api/endpoints";
import type { LogLine } from "../types";
import { appendBounded, emptyRing, type RingState } from "./logRingBuffer";

interface StreamState {
  lines: LogLine[];
  done: boolean;
  /** Plan 156 F3 — cuántas líneas se descartaron por la cota del ring-buffer. */
  dropped?: number;
  error?: string;
  telemetry?: {
    turns?: number | null;
    input_tokens?: number | null;
    output_tokens?: number | null;
    cost_usd?: number | null;
    cost_estimated?: boolean;
  };
}

// Reconnect backoff: 1s → 30s. Después de eso emitimos error definitivo.
const RECONNECT_INITIAL_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

/**
 * Stream SSE de logs de una ejecución.
 *
 * Hardening:
 * - JSON.parse en try/catch: payloads no-JSON o eventos no esperados no
 *   tumban el listener.
 * - Dedup por (timestamp, level, message): si una re-subscripción re-emite
 *   logs ya vistos no se duplican en la UI.
 * - Reconnect automático con backoff exponencial cuando EventSource entra en
 *   estado CLOSED tras un error de red.
 */
export function useExecutionStream(executionId: number | null): StreamState {
  const [state, setState] = useState<StreamState>({ lines: [], done: false });
  const qc = useQueryClient();
  // Plan 156 F3 — ring-buffer persistente entre reconexiones del MISMO
  // executionId: acota `lines` a 5000 y mantiene el Set de dedup en la misma
  // ventana (dedup window == ring window).
  const ring = useRef<RingState>(emptyRing());

  useEffect(() => {
    if (executionId == null) {
      ring.current = emptyRing();
      setState({ lines: [], done: false });
      return;
    }

    ring.current = emptyRing();
    setState({ lines: [], done: false });

    let es: EventSource | null = null;
    let retryMs = RECONNECT_INITIAL_MS;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const onLog = (e: MessageEvent) => {
      let data: LogLine | null = null;
      try {
        const parsed = JSON.parse(e.data);
        if (parsed && typeof parsed === "object") {
          data = parsed as LogLine;
        }
      } catch {
        // payload no-JSON — ignorar silenciosamente
      }
      if (!data) return;

      // Plan 156 F3 — append acotado + dedup en ventana. El `!==` evita el
      // re-render cuando la línea era un duplicado dentro de la ventana.
      const next = appendBounded(ring.current, data);
      if (next !== ring.current) {
        ring.current = next;
        setState((s) => ({ ...s, lines: next.lines, dropped: next.dropped }));
      }
    };

    const onCompleted = (_ev?: MessageEvent) => {
      setState((s) => ({ ...s, done: true }));
      qc.invalidateQueries({ queryKey: ["execution", executionId] });
      qc.invalidateQueries({ queryKey: ["executions"] });
      // Plan 134 F2 (C3): emisor único — el notificador global
      // (useGlobalExecutionNotifier, post-F2) cubre todos los proyectos y
      // estados con contexto rico (proyecto/título vía byId); este stream ya
      // no notifica (evita que el aviso pobre del SSE gane la carrera y el
      // dedup descarte el aviso rico).
      closed = true;
      es?.close();
    };

    const onTelemetry = (e: MessageEvent) => {
      try {
        const parsed = JSON.parse(e.data);
        const data = parsed?.data && typeof parsed.data === "object" ? parsed.data : parsed;
        setState((s) => ({
          ...s,
          telemetry: {
            turns: data?.turns ?? s.telemetry?.turns ?? null,
            input_tokens: data?.input_tokens ?? s.telemetry?.input_tokens ?? null,
            output_tokens: data?.output_tokens ?? s.telemetry?.output_tokens ?? null,
            cost_usd: data?.cost_usd ?? s.telemetry?.cost_usd ?? null,
            cost_estimated: Boolean(data?.cost_estimated),
          },
        }));
      } catch {
        // ignore malformed telemetry payloads
      }
    };

    const scheduleReconnect = () => {
      if (closed) return;
      if (retryMs > RECONNECT_MAX_MS) {
        setState((s) => ({ ...s, error: "stream error — recargá la página" }));
        return;
      }
      retryTimer = setTimeout(() => {
        retryTimer = null;
        connect();
      }, retryMs);
      retryMs = Math.min(retryMs * 2, RECONNECT_MAX_MS + 1);
    };

    const onError = () => {
      if (closed) return;
      // EventSource hace su propio reintento si readyState=CONNECTING, pero si
      // queda CLOSED (cortocircuito de red / servidor 4xx) hay que crear uno nuevo.
      if (es && es.readyState === EventSource.CLOSED) {
        es.close();
        es = null;
        scheduleReconnect();
      }
    };

    const connect = () => {
      es = new EventSource(Executions.streamUrl(executionId));
      es.addEventListener("log", onLog as EventListener);
      es.addEventListener("pre_run", onLog as EventListener);
      es.addEventListener("completed", onCompleted as EventListener);
      es.addEventListener("telemetry", onTelemetry as EventListener);
      es.addEventListener("ping", () => {});
      es.addEventListener("open", () => {
        retryMs = RECONNECT_INITIAL_MS;
      });
      es.onerror = onError;
    };

    connect();

    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      es?.close();
    };
  }, [executionId, qc]);

  return state;
}
