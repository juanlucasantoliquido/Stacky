import { FormEvent, useState } from "react";
import { Maximize2, Minimize2, Send, Terminal, X } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Executions } from "../api/endpoints";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { useWorkbench } from "../store/workbench";
import styles from "./CodexConsoleDock.module.css";

export default function CodexConsoleDock() {
  const executionId = useWorkbench((state) => state.codexConsoleExecutionId);
  const minimized = useWorkbench((state) => state.codexConsoleMinimized);
  const setExecution = useWorkbench((state) => state.setCodexConsoleExecution);
  const setMinimized = useWorkbench((state) => state.setCodexConsoleMinimized);
  const [input, setInput] = useState("");
  const stream = useExecutionStream(executionId);
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

  if (executionId == null) return null;

  const status = executionQ.data?.status;
  const isCodexRun = executionQ.data?.metadata?.runtime === "codex_cli";
  const canSend = isCodexRun && !sendInput.isPending && input.trim().length > 0;
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

  return (
    <section className={minimized ? styles.dockMinimized : styles.dock} aria-label="Consola Codex">
      <header className={styles.header}>
        <div className={styles.title}>
          <Terminal size={16} />
          <span>Codex</span>
          <span className={styles.execution}>#{executionId}</span>
          <span className={stream.done ? styles.done : styles.running}>
            {statusLabel}
          </span>
        </div>
        <div className={styles.actions}>
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
            onClick={() => setExecution(null)}
            title="Cerrar consola"
          >
            <X size={15} />
          </button>
        </div>
      </header>

      {!minimized && (
        <div className={styles.body}>
          {stream.lines.length === 0 ? (
            <div className={styles.empty}>Esperando salida...</div>
          ) : (
            stream.lines.map((line, index) => (
              <div
                key={`${line.timestamp}-${index}`}
                className={`${styles.line} ${styles[line.level] ?? ""}`}
              >
                <span className={styles.level}>{line.level}</span>
                {line.group && <span className={styles.group}>{line.group}</span>}
                <span className={styles.message}>{line.message}</span>
              </div>
            ))
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

      {!minimized && isCodexRun && (
        <form
          className={styles.inputBar}
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const text = input.trim();
            if (text) sendInput.mutate(text);
          }}
        >
          <textarea
            className={styles.input}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Responder a Codex..."
            rows={1}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                const text = input.trim();
                if (text) sendInput.mutate(text);
              }
            }}
          />
          <button
            type="submit"
            className={styles.sendButton}
            disabled={!canSend}
            title="Enviar a Codex"
          >
            <Send size={15} />
          </button>
        </form>
      )}
    </section>
  );
}
