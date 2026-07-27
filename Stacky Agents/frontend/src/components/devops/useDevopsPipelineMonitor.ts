/**
 * useDevopsPipelineMonitor.ts — Plan 103 F2.
 *
 * Sondea el último pipeline disparado y mantiene vivo el badge del header.
 *
 * DOCTRINA DE SONDEO (Plan 239 F6): ningún sondeo del panel DevOps puede correr
 * cuando no se está mirando. Este hook vive en el SHELL a propósito (tiene que
 * sobrevivir al cambio de sub-sección, que es el problema que el plan resuelve),
 * así que no puede gatearse por `ctx.visible`. Se gatea por VISIBILIDAD DEL
 * DOCUMENTO: se pausa con la pestaña del navegador en segundo plano y se reanuda
 * al volver al frente.
 *
 * La reanudación no es opcional: el 239 F6 documenta que pausar sin reanudar es
 * "peor que sondear de más" (el sondeo no vuelve nunca y el badge queda congelado
 * mintiendo). Por eso el listener de `visibilitychange` fuerza la re-evaluación.
 *
 * Usa `setTimeout` re-armado, NO `setInterval`: el intervalo cambia en cada vuelta
 * (backoff 3s→5s→10s→30s).
 */
import { useEffect, useState } from 'react';
import { CIPipeline } from '../../api/endpoints';
import {
  computeBackoffMs,
  isTerminalStatus,
  isPollCapError,
  useDevopsMonitorStore,
} from '../../devops/pipelineMonitor';

/** `true` si la pestaña está al frente. Fuera del navegador, asumir que sí. */
function documentoVisible(): boolean {
  if (typeof document === 'undefined') return true;
  return document.visibilityState === 'visible';
}

export function useDevopsPipelineMonitor(enabled: boolean): void {
  const last = useDevopsMonitorStore((s) => s.last);
  const attempt = useDevopsMonitorStore((s) => s.attempt);
  const updateStatus = useDevopsMonitorStore((s) => s.updateStatus);
  const bumpAttempt = useDevopsMonitorStore((s) => s.bumpAttempt);

  // Espejo del estado de la pestaña. Al cambiar, el efecto de abajo se re-evalúa
  // ⇒ el sondeo se REANUDA solo al volver al frente.
  const [visible, setVisible] = useState(documentoVisible);
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const onChange = () => setVisible(documentoVisible());
    document.addEventListener('visibilitychange', onChange);
    return () => document.removeEventListener('visibilitychange', onChange);
  }, []);

  const pipelineId = last?.pipelineId ?? null;
  const project = last?.project ?? '';
  const status = last?.status ?? null;

  useEffect(() => {
    // Guard de visibilidad de la pestaña: con el documento oculto NO se sondea.
    if (!enabled || !pipelineId || !visible) return;
    // El pipeline ya terminó: se deja de sondear y NUNCA se re-arranca solo.
    if (isTerminalStatus(status)) return;

    let cancelado = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const res = await CIPipeline.monitor(project, pipelineId);
        if (cancelado) return;
        updateStatus(res.status, res.web_url);
      } catch (e: unknown) {
        if (cancelado) return;
        // 429 del cap de polls: NO es un fallo del pipeline. No toca el tono ni el
        // mensaje del badge; solo relaja el ritmo, que es lo que el backend pide.
        if (isPollCapError(e)) bumpAttempt();
        else bumpAttempt(); // otro error transitorio: también relajar y reintentar
      } finally {
        if (!cancelado) timer = setTimeout(() => void tick(), computeBackoffMs(attempt));
      }
    };

    timer = setTimeout(() => void tick(), computeBackoffMs(attempt));
    return () => {
      cancelado = true;
      if (timer) clearTimeout(timer);
    };
    // `visible` EN LAS DEPS: sin esto el efecto no se re-evalúa al volver al frente
    // y el sondeo no se reanuda (Plan 239 F6).
  }, [enabled, pipelineId, project, status, visible, attempt, updateStatus, bumpAttempt]);
}
