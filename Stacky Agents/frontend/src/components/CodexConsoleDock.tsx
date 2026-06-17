import { FormEvent, useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2, Send, Terminal, X } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Executions } from "../api/endpoints";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { useWorkbench } from "../store/workbench";
import type { LogLine } from "../types";
import ExecutionDetailDrawer from "./ExecutionDetailDrawer";
import styles from "./CodexConsoleDock.module.css";

/** Distancia (px) al fondo dentro de la cual seguimos auto-scrolleando. */
const AUTOSCROLL_THRESHOLD = 48;

/** ¿La línea la escribió el operador (vos) en vez del agente / sistema? */
function isOperatorLine(line: LogLine): boolean {
  return (line.group ?? "").toLowerCase().includes("operator");
}

/** ¿La línea la emitió el agente CLI (claude-code / codex)? */
function isAgentLine(line: LogLine): boolean {
  const group = (line.group ?? "").toLowerCase();
  return group.includes("claude") || group.includes("codex");
}

/**
 * Texto de fase "en vivo" derivado de los propios eventos del stream, para no
 * mostrar una caja vacía mientras el runner enriquece contexto o espera al
 * modelo. Devuelve null cuando ya no corresponde mostrar el banner de trabajo.
 */
function workingPhase(
  lines: LogLine[],
  running: boolean,
  agentLabel: string
): string | null {
  if (!running) return null;
  if (lines.length === 0) return "Conectando con la consola…";

  // Buscamos hacia atrás la última pista de fase que emitió el backend.
  for (let i = lines.length - 1; i >= 0; i--) {
    const msg = (lines[i].message ?? "").toLowerCase();
    if (msg.includes("enriqueci")) return "Enriqueciendo contexto…";
    if (msg.includes("prompt inicial")) return `Esperando a ${agentLabel}…`;
    if (msg.includes("esperando")) return `Esperando a ${agentLabel}…`;
    if (isAgentLine(lines[i])) return `${agentLabel} está escribiendo…`;
  }
  return `${agentLabel} está trabajando…`;
}

export default function CodexConsoleDock() {
  const executionId = useWorkbench((state) => state.codexConsoleExecutionId);
  const minimized = useWorkbench((state) => state.codexConsoleMinimized);
  const setExecution = useWorkbench((state) => state.setCodexConsoleExecution);
  const setMinimized = useWorkbench((state) => state.setCodexConsoleMinimized);
  const [input, setInput] = useState("");
  const [detailOpen, setDetailOpen] = useState(false);
  const stream = useExecutionStream(executionId);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  // Mientras el usuario esté pegado al fondo, seguimos auto-scrolleando; si
  // scrollea hacia arriba para leer, dejamos de moverle la vista.
  const stickToBottom = useRef(true);
  const executionQ = useQuery({
    queryKey: ["codex-console-execution", executionId],
    queryFn: () => Executions.byId(executionId!),
    enabled: executionId != null,
    refetchInterval: stream.done ? false : 5000,
  });
  const sendInput = useMutation({
    mutationFn: (text: string) => Executions.sendCodexInput(executionId!, text),
    onSuccess: () => setInput(""),
  });

  const status = executionQ.data?.status;
  const runtime = executionQ.data?.metadata?.runtime;
  const isClaudeRun = runtime === "claude_code_cli";
  const isInteractiveRun = runtime === "codex_cli" || isClaudeRun;
  const runtimeLabel = isClaudeRun ? "Claude Code" : "Codex";
  const isRunning = status === "running" && !stream.done;

  // Auto-scroll al fondo cuando llegan líneas nuevas, salvo que el usuario
  // haya scrolleado hacia arriba para leer historial.
  useEffect(() => {
    const el = bodyRef.current;
    if (!el || minimized || !stickToBottom.current) return;
    el.scrollTop = el.scrollHeight;
  }, [stream.lines.length, minimized]);

  // Al abrir una consola interactiva, traemos el foco al textarea para que
  // responder sea inmediato (sin tener que ir a buscar el input).
  useEffect(() => {
    if (executionId != null && isInteractiveRun && !minimized) {
      textareaRef.current?.focus();
    }
  }, [executionId, isInteractiveRun, minimized]);

  if (executionId == null) return null;

  // Ambos runtimes CLI aceptan respuestas del operador por stdin.
  const canSend =
    isInteractiveRun &&
    !stream.done &&
    status === "running" &&
    !sendInput.isPending &&
    input.trim().length > 0;
  const sessionEnded = stream.done || status !== "running";
  const phase = workingPhase(stream.lines, isRunning, runtimeLabel);
  const totalTokens =
    (stream.telemetry?.input_tokens ?? 0) +
    (stream.telemetry?.output_tokens ?? 0);
  const statusLabel =
    status === "queued"
      ? "preparado"
      : status === "running"
        ? "corriendo"
        : status === "error"
          ? "error"
          : stream.done || status === "completed"
            ? "finalizada"
            : "abierta";

  const handleScroll = () => {
    const el = bodyRef.current;
    if (!el) return;
    stickToBottom.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < AUTOSCROLL_THRESHOLD;
  };

  return (
    <>
    <section className={minimized ? styles.dockMinimized : styles.dock} aria-label={`Consola ${runtimeLabel}`}>
      <header className={styles.header}>
        <div className={styles.title}>
          <Terminal size={16} />
          <span>{runtimeLabel}</span>
          <span className={styles.execution}>#{executionId}</span>
          <span className={stream.done ? styles.done : styles.running}>
            {statusLabel}
          </span>
          {stream.telemetry?.turns != null && (
            <span className={styles.execution}>🔁 {stream.telemetry.turns}</span>
          )}
          {totalTokens > 0 && (
            <span className={styles.execution}>⎁ {totalTokens.toLocaleString()}</span>
          )}
          {stream.telemetry?.cost_usd != null && (
            <span className={styles.execution}>
              ${Number(stream.telemetry.cost_usd).toFixed(4)}
              {stream.telemetry?.cost_estimated ? " est" : ""}
            </span>
          )}
        </div>
        <div className={styles.actions}>
          {stream.done && (
            <button
              type="button"
              className={styles.iconButton}
              onClick={() => setDetailOpen(true)}
              title="Ver detalle de ejecución"
            >
              Ver detalle
            </button>
          )}
          <button
            type="button"
            className={styles.iconButton}
            onClick={() => setMinimized(!minimized)}
            title={minimized ? "Expandir consola" : "Minimizar consola"}
          >
            {minimized ? <Maximize2 size={15} /> : <Minimize2 size={15} />}
          </button>
          <button
            type="button"
            className={styles.iconButton}
            onClick={() => {
              // En una sesión interactiva viva, cerrar la consola finaliza la
              // sesión (cierra stdin → el agente termina). Para sólo ocultarla
              // sin matarla, usar minimizar.
              if (isInteractiveRun && status === "running" && !stream.done) {
                void Executions.cancel(executionId).catch(() => {});
              }
              setExecution(null);
            }}
            title="Cerrar consola (finaliza la sesión)"
          >
            <X size={15} />
          </button>
        </div>
      </header>

      {!minimized && (
        <div className={styles.body} ref={bodyRef} onScroll={handleScroll}>
          {stream.lines.map((line, index) => {
            const role = isOperatorLine(line)
              ? styles.lineOperator
              : isAgentLine(line)
                ? styles.lineAgent
                : "";
            return (
              <div
                key={`${line.timestamp}-${index}`}
                className={`${styles.line} ${styles[line.level] ?? ""} ${role}`}
              >
                <span className={styles.level}>{line.level}</span>
                {line.group && <span className={styles.group}>{line.group}</span>}
                <span className={styles.message}>{line.message}</span>
              </div>
            );
          })}
          {phase && (
            <div className={styles.phase} role="status" aria-live="polite">
              <span className={styles.spinner} aria-hidden="true" />
              <span>{phase}</span>
            </div>
          )}
          {sendInput.error && (
            <div className={`${styles.line} ${styles.error}`}>
              <span className={styles.level}>ERROR</span>
              <span className={styles.group}>operator</span>
              <span className={styles.message}>{sendInput.error.message}</span>
            </div>
          )}
        </div>
      )}

      {!minimized && isInteractiveRun && (
        <form
          className={styles.inputBar}
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const text = input.trim();
            if (text && canSend) sendInput.mutate(text);
          }}
        >
          <textarea
            ref={textareaRef}
            className={styles.input}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            disabled={sessionEnded}
            placeholder={
              sessionEnded
                ? `La sesión de ${runtimeLabel} terminó — no se puede responder`
                : `Escribile a ${runtimeLabel} y Enter para enviar`
            }
            rows={1}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                const text = input.trim();
                if (text && canSend) sendInput.mutate(text);
              }
            }}
          />
          <button
            type="submit"
            className={styles.sendButton}
            disabled={!canSend}
            title={
              sessionEnded
                ? `La sesión de ${runtimeLabel} ya terminó`
                : `Enviar a ${runtimeLabel}`
            }
          >
            <Send size={15} />
          </button>
        </form>
      )}
    </section>
    {detailOpen && (
      <ExecutionDetailDrawer
        executionId={executionId}
        onClose={() => setDetailOpen(false)}
      />
    )}
    </>
  );
}
