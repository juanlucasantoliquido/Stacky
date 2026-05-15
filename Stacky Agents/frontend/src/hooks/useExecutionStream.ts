import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Executions } from "../api/endpoints";
import type { LogLine } from "../types";

interface StreamState {
  lines: LogLine[];
  done: boolean;
  error?: string;
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
  // Set persistente entre reconexiones del MISMO executionId para dedup.
  const seenKeys = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (executionId == null) {
      seenKeys.current = new Set();
      setState({ lines: [], done: false });
      return;
    }

    seenKeys.current = new Set();
    setState({ lines: [], done: false });

    let es: EventSource | null = null;
    let retryMs = RECONNECT_INITIAL_MS;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const dedupKey = (data: LogLine): string =>
      `${data.timestamp ?? ""}|${data.level ?? ""}|${data.message ?? ""}`;

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

      const key = dedupKey(data);
      if (seenKeys.current.has(key)) return;
      seenKeys.current.add(key);

      setState((s) => ({ ...s, lines: [...s.lines, data!] }));
    };

    const onCompleted = () => {
      setState((s) => ({ ...s, done: true }));
      qc.invalidateQueries({ queryKey: ["execution", executionId] });
      qc.invalidateQueries({ queryKey: ["executions"] });
      closed = true;
      es?.close();
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
      es.addEventListener("completed", onCompleted as EventListener);
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
